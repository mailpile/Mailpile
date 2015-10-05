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

var ajaxable_commands = ['search', 'ls', 'profiles'];
var refresh_history = {};
var U = Mailpile.API.U;

var refresh_timer;
var refresh_interval = (5 * 1000) + (Math.random() * 2000);


ajaxable_url = function(url) {
    return (url && ((url.indexOf(U("/in/")) == 0) ||
                    (url.indexOf(U("/browse/")) == 0) ||
                    (url.indexOf(U("/thread/")) == 0) ||
                    (url.indexOf(U("/profiles/")) == 0) ||
                    (url.indexOf(U("/search/")) == 0)));
};

_outerHTML = function(elem) {
    return $('<div />').append(elem.clone()).html();
};

_scroll_up = function(elem) {
    setTimeout(function() { $(elem).scrollTop(0); }, 10);
};

get_now = function() {
    if (Date.now) return Date.now();
    return new Date().getTime()
};

clear_selection_state = function() {
    // FIXME: Is this sufficient?
    Mailpile.messages_cache = [];
};

can_refresh = function(cid) {
    // By default we disable all refreshes of the UI if the user is busy
    // selecting or rearranging or dragging... .
    // FIXME: Hmm, seems other parts of the app should be able to block
    //        updates somewhat granularly.
    // FIXME: Should we just monitor for mouse/keyboard activity and only
    //        update if user isn't doing anything in particular?
    if (cid.indexOf('-tags') != -1) return true;
    return ($('.pile-results input[type=checkbox]:checked').length < 1);
};

prepare_new_content = function(selector) {
    $(selector).find('a').each(function(idx, elem) {
        // FIXME: Should we add some majick to avoid dup click handlers?
        var url = $(elem).attr('href');
        var jhtml = ajaxable_url(url);
        if (elem.className.indexOf('auto-modal') == -1) {
            $(elem).click(function(ev) {
                // We don't hijack events that spawn new tabs/windows etc.
                if (!(ev.ctrlKey || ev.altKey || ev.shiftKey)) {
                    ev.preventDefault();
                    // If we have any composers on the page, save contents
                    // before continuing - whether we're JHTMLing or not!
                    Mailpile.Composer.AutosaveAll(0, function() {
                        if (!(jhtml && update_using_jhtml(url, _scroll_up))) {
                            document.location.href = url;
                        }
                    });
                }
            });
        }
    });
    var $form = $(selector).find('form#form-search');
    $form.submit(function(ev) {
        // We don't hijack events that spawn new tabs/windows etc.
        if (!(ev.ctrlKey || ev.altKey || ev.shiftKey)) {
            if (update_using_jhtml(U("/search/?") + $form.serialize(), _scroll_up)) {
                ev.preventDefault();
            }
        }
    });
};
Mailpile.UI.content_setup.push(prepare_new_content);

restore_state = function(ev) {
    if (ev.state && ev.state.autoajax) {
        $('#content-view').parent().replaceWith(ev.state.html).show();
        clear_selection_state();
        Mailpile.UI.prepare_new_content($('#content-view').parent());
        Mailpile.render();
    }
};

update_using_jhtml = function(original_url, callback) {
    if (ajaxable_url(document.location.pathname)) {
        var cv = $('#content-view').parent();
        history.replaceState({autoajax: true, html: _outerHTML(cv)},
                             document.title);
        cv.hide();
        return $.ajax({
            url: Mailpile.API.jhtml_url(original_url, 'content'),
            type: 'GET',
            success: function(data) {
                history.pushState({autoajax: true, html: data['result']},
                                  data['message'], original_url);
                cv.replaceWith(data['result']).show();
                clear_selection_state();
                cv = $('#content-view');
                Mailpile.UI.prepare_new_content(cv.parent());
                Mailpile.render();
                if (callback) { callback(cv) };
            },
            error: function() {
                cv.show();
            }
        });
    }
    return false;
};

refresh_from_cache = function(cid) {
    var $inpage = $('.content-'+cid);
    if ($inpage.length > 0) {
        refresh_history[cid] = -1; // Avoid thrashing
        Mailpile.API.cached_get({
            id: cid,
            _output: Mailpile.API.jhtml_url($inpage.data('template')
                                            || 'as.html')
        }, function(json) {
             if (json.result) {
                 var cid = json.state.cache_id;
                 $('.content-'+cid).replaceWith(json.result);
                 Mailpile.UI.prepare_new_content('.content-'+cid);
                 refresh_history[cid] = get_now();
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

    // Figure out which elements on the page exist in cache, initialized
    // our refresh_history timers to match...
    $('.cached').each(function(i, elem) {
        var classlist = elem.className.split(/\s+/);
        for (var i in classlist) {
            var cn = classlist[i];
            if (cn.indexOf('content-') == 0) {
                var cid = cn.substring(8);
                refresh_history[cid] = get_now();
                console.log('refresh_history['+cid+'] =' + get_now());
            }
        }
    });

    // Subscribe to the event-log, to freshen up UI elements as soon as
    // possible.
    EventLog.subscribe('.command_cache.CommandCache', function(ev) {
        for (var cidx in ev.data.cache_ids) {
            var cid = ev.data.cache_ids[cidx];
            if (can_refresh(cid)) {
                refresh_from_cache(cid);
            }
            else {
               refresh_history[cid] = 0; // Mark as needing a refresh!
            }
            refresh_interval = 2000;
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
                }
            }
        }
        if (refresh_interval < 60000) {
            refresh_interval += 1000 * Math.random();
        }
    });
    refresh_timer.set({ time: 950, autostart: true });
});

return {
    'timer': refresh_timer,
    'history': refresh_history,
    'update_using_jhtml': update_using_jhtml,
    'refresh_from_cache': refresh_from_cache,
    'prepare_new_content': prepare_new_content
}
