/*
 * This code seamlessly upgrades any <a href=...> which would cause a search
 * to happen, to instead trigger an AJAX load.  This should make searches
 * feel almost instantaneous, while allowing us to keep all the template
 * logic in the back-end as Jinja2.
 *
 * FIXME:
 *   - Invoke any logic pertaining to display modes before updating
 *   - Use pushstate to update the browser history and location bar
 */

var get_now;
var clear_selection_state;
var can_refresh;
var update_using_jhtml;
var prepare_new_content;
var refresh_from_cache;

var refresh_history = {};
var U = Mailpile.API.U;

var refresh_timer;
var backup_refresh_interval = (30 * 1000) + (Math.random() * 2000);
var refresh_interval = backup_refresh_interval;


ajaxable_url = function(url) {
    return (url &&
            ((url.indexOf(U("/in/")) == 0) ||
             (url.indexOf(U("/browse/")) == 0) ||
             (url.indexOf(U("/thread/")) == 0) ||
             (url.indexOf(U("/profiles/")) == 0) ||
             (url.indexOf(U("/message/compose/")) == 0) ||
             (url.indexOf(U("/settings/")) == 0) ||
             (url.indexOf(U("/crypto/tls/getcert/")) == 0) ||
             (url.indexOf(U("/logs/")) == 0) ||
             (url.indexOf(U("/page/")) == 0) ||
             (url.indexOf(U("/search/")) == 0)
             ) && url);
};

_outerHTML = function(elem) {
    return $('<div />').append(elem.clone()).html();
};

_scroll_up = function(elem, scrollto) {
    setTimeout(function() {
      $(elem).find('div, table, tbody, p').scrollTop(0);
      $('#content-view, #content-tall-view').eq(0).scrollTop(scrollto || 0);
    }, 10);
};

get_now = function() {
    if (Date.now) return Date.now();
    return new Date().getTime()
};

clear_selection_state = function() {
  Mailpile.UI.Selection.select_none();
};

get_selection_state = function() {
  var selected = Mailpile.UI.Selection.selected('.pile-results');
  var elements = {};
  $.each(selected, function() {
    if (this != '!all') {
      elements[this] = $('.pile-results .pile-message-' + this).eq(0).clone();
    }
  });
  return {
    selected: selected,
    elements: elements
  };
};

restore_selection_state = function(sstate) {
  if (sstate.selected.length) {
    $.each(sstate.selected.reverse(), function() {
      if (this != '!all') {
        if ($('.pile-results .pile-message-' + this).length < 1) {
          var elem = sstate.elements[this];
          if (elem && $(elem).find('.message-container').length < 1) {
            $('.pile-results .pile-message').eq(0).parent().prepend(elem);
          }
        }
      }
      Mailpile.pile_action_select($('.pile-results .pile-message-' + this), 'partial');
    });
    Mailpile.bulk_actions_update_ui();
  }
};

can_refresh = function(cid) {
    // Disable checks below (experimental)
    return (Mailpile.ui_in_action < 1);

    // By default we disable all refreshes of the UI if the user is busy
    // selecting or rearranging or dragging... .
    // FIXME: Hmm, seems other parts of the app should be able to block
    //        updates somewhat granularly.
    // FIXME: Should we just monitor for mouse/keyboard activity and only
    //        update if user isn't doing anything in particular?
    return ((Mailpile.ui_in_action < 1) &&
            ($('.pile-results input[type=checkbox]:checked').length < 1));
};

autoajax_go = function(url, message, jhtml, noblank, noscroll, selrestore) {
    url = Mailpile.fix_url(url);
    if (jhtml === undefined) jhtml = ajaxable_url(url);

    // Provide UI feedback if this takes time
    var done = Mailpile.notify_working(message, (noblank) ? 250 : 1500);

    // Attempt to preserve selections cross-refresh.
    var selected = get_selection_state();

    // If noscroll is requested, try to preserve scroll position.
    if (noscroll) {
      scrollto = $('#content-view, #content-tall-view').eq(0).scrollTop();
    }
    else scrollto = 0;

    // Called after the page is updated
    var scroll_and_done = function(stuff) {
      done();
      if (selrestore) {
        restore_selection_state(selected);
      }
      else {
        clear_selection_state(selected);
      }
      return _scroll_up(stuff, scrollto);
    }

    // If we have any composers on the page, save contents
    // before continuing - whether we're JHTMLing or not!
    Mailpile.Composer.AutosaveAll(0, function() {
        if (!(jhtml && update_using_jhtml(url, scroll_and_done, done, noblank))) {
            document.location.href = url;
        }
    });
};

prepare_new_content = function(selector) {
    $(selector).find('a').each(function(idx, elem) {
        // FIXME: Should we add some majick to avoid dup click handlers?
        var url = $(elem).attr('href');
        var jhtml = ajaxable_url(url);
        if (url &&
                (url.indexOf('#') != 0) &&
                (url.indexOf('mailto:') != 0) &&
                (url.indexOf('javascript:') != 0) &&
                (elem.target != '_blank') &&
                (elem.className.indexOf('auto-modal') == -1)) {
            $(elem).click(function(ev) {
                // We don't hijack events that spawn new tabs/windows etc.
                if (!(ev.ctrlKey || ev.altKey || ev.shiftKey)) {
                    ev.preventDefault();
                    var $elem = $(elem);
                    autoajax_go(url, undefined, jhtml,
                                $elem.data('noblank') ? true : false,
                                $elem.data('noscroll') ? true : false,
                                $elem.data('keep-selection') ? true : false);
                }
            });
        }
    });
    var $form = $(selector).find('form#form-search');
    $form.submit(function(ev) {
        // We don't hijack events that spawn new tabs/windows etc.
        if (!(ev.ctrlKey || ev.altKey || ev.shiftKey)) {
            var selected = get_selection_state();
            if (update_using_jhtml(U("/search/?") + $form.serialize(),
                                   function(stuff) {
                // Always restore selection state on search, as searching
                // is actually a moderately advanced behaviour.
                restore_selection_state(selected);
                return _scroll_up(stuff);
            })) {
                ev.preventDefault();
            }
        }
    });
};
Mailpile.UI.content_setup.push(prepare_new_content);

render_result = function(data, cv, html) {
    var cv = cv || $('#content-view, #content-tall-view').parent();

    if (data) Mailpile.update_title(data['message']);
    cv.replaceWith(html || data['result']).show();

    clear_selection_state();
    cv = $('#content-view, #content-tall-view').parent();
    Mailpile.UI.prepare_new_content(cv);
    Mailpile.render();
    // Work around bugs in drag/drop lib, nuke artefacts
    $('div.ui-draggable-dragging').remove();

    return cv;
};

restore_state = function(ev) {
    if (ev.state && ev.state.autoajax) {
        update_using_jhtml(ev.state.url, function(cv) {
                 // Success!
            }, function(cv) {
                 // Error?
            }, false, true
        );
    }
};

update_using_jhtml = function(original_url, callback, error_callback,
                              noblank, nohistory) {
    if (ajaxable_url(document.location.pathname)) {
        var cv = $('#content-view, #content-tall-view').parent();
        if (!noblank) cv.hide();
        if (!nohistory)
            history.replaceState({autoajax: true, url: document.location.href},
                                 document.title);
        return $.ajax({
            url: Mailpile.API.jhtml_url(original_url, 'content'),
            timeout: Mailpile.ajax_timeout,
            type: 'GET',
            success: function(data) {
                if (!nohistory)
                    history.pushState({autoajax: true, url: original_url},
                                      data['message'], original_url);
                shown = render_result(data, cv)
                if (callback) { callback(shown) };
            },
            error: function() {
                if (error_callback) error_callback(cv);
                cv.show();
            }
        });
    }
    return false;
};

refresh_from_cache = function(cid) {
    var $inpage = $('.content-'+cid);
    if ($inpage.length > 0 && ($inpage.closest('#modal-full').length < 1)) {
        console.log('Updating from cache: ' + cid);
        refresh_history[cid] = -1; // Avoid thrashing
        Mailpile.API.cached_get({
            id: cid,
            _output: Mailpile.API.jhtml_url($inpage.data('template')
                                            || 'as.html')
        }, function(json) {
             if (json.result) {
                 var cid = json.state.cache_id;
                 if (can_refresh(cid)) {
                     var selected = get_selection_state();
                     $('.content-'+cid).replaceWith(json.result.trim());
                     Mailpile.UI.prepare_new_content('.content-'+cid);
                     restore_selection_state(selected);
                     refresh_history[cid] = get_now();
                     // Work around bugs in drag/drop lib, nuke artefacts
                     $('div.ui-draggable-dragging').remove();
                 }
                 else {
                     // Result discarded, mark as needing a refresh!
                     console.log('Result discarded, will try again for ' + cid);
                     refresh_history[cid] = 0;
                 }
             }
             else {
                 console.log('Failed to load from cache!');
             }
        });
        return true;
    }
    else if (refresh_history[cid]) {
        delete refresh_history[cid];
    }
    return false;
};

$(document).ready(function() {
    // Set up our onpopstate handler
    window.onpopstate = restore_state;

    Mailpile.go = autoajax_go;

    // Figure out which elements on the page exist in cache, initialized
    // our refresh_history timers to match...
    $('.cached').each(function(i, elem) {
        var classlist = elem.className.split(/\s+/);
        for (var i in classlist) {
            var cn = classlist[i];
            if (cn.indexOf('content-') == 0) {
                var cid = cn.substring(8);
                refresh_history[cid] = get_now();
                console.log('refresh_history['+cid+'] = ' + refresh_history[cid]);
            }
        }
    });

    // Subscribe to the event-log, to freshen up UI elements as soon as
    // possible.
    EventLog.subscribe('.command_cache.CommandCache', function(ev) {
        var now = get_now();
        for (var cidx in ev.data.cache_ids) {
            var cid = ev.data.cache_ids[cidx];
            refresh_history[cid] = 0; // Mark as needing a refresh!
            // If the event log is reporting things actively, lower the
            // force-refresh interval as it's probably not needed.
            if (refresh_interval < 120000) {
                refresh_interval += 1000 * Math.random();
            }
        }
    });

    // As a backup, attempt to refresh all UI elements periodically
    refresh_timer = $.timer(function() {
        var now = get_now();
        for (var cid in refresh_history) {
            if ((refresh_history[cid] >= 0) &&
                    (refresh_history[cid] < now - refresh_interval)) {
                if (can_refresh(cid)) {
                    refresh_from_cache(cid);
                    return;
                }
            }
        }
        // If we get this far, nothing was refreshed, might need to
        // force things.
        if (refresh_interval > backup_refresh_interval) {
            refresh_interval -= 1000 * Math.random();
        }
    });
    refresh_timer.set({ time: 750, autostart: true });
});

return {
    'timer': refresh_timer,
    'history': refresh_history,
    'update_using_jhtml': update_using_jhtml,
    'refresh_from_cache': refresh_from_cache,
    'prepare_new_content': prepare_new_content
}
