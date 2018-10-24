Mailpile.bulk_actions_update_ui = function() {
  $('.selection-context').each(function (i, context) {
    var $context = $(context);
    var selected = Mailpile.UI.Selection.selected($context);
    var checkboxes = $context.find('.pile-results input[type=checkbox]');

    // This is a hack to make sure the length check below fails
    if (checkboxes.length == 0) checkboxes = ['fake', 'fake'];

    // Reset state...
    Mailpile.hide_message_hints($context);
    if ((selected.length < 1) || (selected[0] !== "!all")) {
      $context.find('#pile-select-all-action').val('');
    }
    if ((selected.length == checkboxes.length) ||
        (selected[0] == '!all')) {
      $context.find('#pile-select-all-action').prop('checked', true);
    }
    else {
      $context.find('#pile-select-all-action').prop('checked', false);
    }

    Mailpile.update_selection_classes($context.find('td.checkbox'));

    if (selected.length > 0) {
      var message = ('<span id="bulk-actions-selected-count">' +
                       Mailpile.UI.Selection.human_length(selected) +
                     '</span> ');
      if (selected[0] == "!all") {
        message = ('<a onclick="javascript:Mailpile.unselect_all_matches(this);">' +
                     '<span class="icon-star"></span> ' +
                     $context.find('#bulk-actions-message').data('unselect_all') +
                   '</a>');
      }
      else if ($context.find("#pile-select-all-action").is(':checked')) {
        message = ('<a onclick="javascript:Mailpile.select_all_matches(this);">' +
                     message + ' ' +
                     $context.find('#bulk-actions-message').data('select_all') +
                   '</a>');
      }
      else {
        message += $context.find('#bulk-actions-message').data('bulk_selected');
        Mailpile.show_related_search_link($context, selected);
      }
      $context.find('#bulk-actions-message').addClass('mobile-hide').html(message);
      $context.find('.sub-navigation').addClass('mobile-hide');
      $context.find('.bulk-actions').removeClass('mobile-hide');

      var have_tags = {};
      for (var i = 0; i < selected.length; i++) {
        var search = '.pile-message-' + selected[i];
        if (selected[i] == "!all") search = '.pile-message';
        var tids = $context.find(search).data('tids').split(/,/);
        for (var j = 0; j < tids.length; j++) have_tags[tids[j]] = true;
      }

      Mailpile.show_bulk_actions($context.find('.bulk-actions').find('li'),
                                 have_tags);
    }
    else {
      var message = $context.find('#bulk-actions-message').data('bulk_selected_none');
      $context.find('#bulk-actions-message').removeClass('mobile-hide').html(message);
      Mailpile.hide_bulk_actions($context.find('.bulk-actions').find('li.hide'));
      $context.find('.sub-navigation').removeClass('mobile-hide');
      $context.find('.bulk-actions').addClass('mobile-hide');
    }
  });
};


Mailpile.hide_message_hints = function($context) {
  $context.find('div.bulk-actions-hints').html('').on('click', undefined);
};


Mailpile.show_related_search_link = function($context, selected) {
  if (selected && (selected.length < 4) && (selected[0] != '!all')) {
    $context.find('div.bulk-actions-hints').html(
      '<a><span class="icon-search"></span>' +
      ' {{_("Search for Similar E-mail")}}</a>').off('click').on('click',
    function() {
      var stoplist = {{ ('%s' % stoplist|list)|safe }};
      var data = {
        qq: function(p, t, cutoff) {
          // Warning: This is the same as mailpile.utils.WORD_REGEXP
          //          and they need to be kept in sync.
          var qt = t.replace(
            /[\s\!@#$%^&*\(\)_+=\{\}\[\]:\"|;`\'\\\<\>\?,\.\/\-]/g, ' '
            ).split(/ +/
            ).filter(function(w) {
              return ((stoplist.indexOf(w.toLowerCase()) < 0) &&
                      (w.length > 1))}
            ).sort(function(a, b) {
              return (a.length < b.length)}
            ).slice(0, (cutoff || 3));
          if (p && p.length) return p + ':' + qt.join(' ' + p + ':');
          return qt.join(' ');
        },
        q: function(p, t, cutoff) {
          t = t.split(/ +/
            ).sort(function(a, b) {
              return (a.length < b.length)}
            ).slice(0, (cutoff || 3));
          return p + ':' + t.join(' ' + p + ':');
        },
        trunc: function(s, len) {
          if (s.length > (len-3)) return s.substring(0, (len-3)) + ' ...';
          return s;
        },
        subjects: [],
        lists: [],
        emails: [],
        froms: [],
        muas: [],
        hpts: [],
        hpss: [],
        extras: ''};

      var date_start = '';
      var date_end = '';

      $.each(selected, function(i, mid) {
        var $msg = $('tr.pile-message-' + mid);
        var from = $msg.find('td.from').data('address');
        var subj = $msg.find('.message-subject').html();
        if (!subj) subj = $msg.find('.subject a').html();
        data.subjects.push(subj);
        if (data.emails.indexOf(from) < 0) data.emails.push(from);
        $.each($msg.data('to-cc').split(/ /), function(i, email) {
          if (email && (data.emails.indexOf(email) < 0)) {
            data.emails.push(email);
          }
        });
        if (data.froms.indexOf(from) < 0) data.froms.push(from);
        data.lists.push($msg.data('list'));
        data.muas.push($msg.data('mua'));
        data.hpts.push($msg.data('mua-fingerprint'));
        data.hpss.push($msg.data('sender-fingerprint'));
        var ts = $msg.find('td.date').data('ts');
        if (!date_start || (ts < date_start)) date_start = ts;
        if (!date_end || (ts > date_end)) date_end = ts;

        // FIXME: Add more special cases
        if (from == 'notifications@github.com') {
          data.extras = $msg.find('td.from').data('fn');
        }
      });

      var d4s = new Date((date_start - (24 * 3600 * 14)) * 1000);
      var d4e = new Date((date_end + (24 * 3600 * 14)) * 1000);
      data.date_range_4wks = (
        d4s.getFullYear() + '-' +
        (d4s.getMonth()+1) + '-' +
        d4s.getDate() + '..' +
        d4e.getFullYear() + '-' +
        (d4e.getMonth() + 1) + '-' +
        d4e.getDate());

      var d2s = new Date((date_start - (24 * 3600 * 7)) * 1000);
      var d2e = new Date((date_end + (24 * 3600 * 7)) * 1000);
      data.date_range_2wks = (
        d2s.getFullYear() + '-' +
        (d2s.getMonth()+1) + '-' +
        d2s.getDate() + '..' +
        d2e.getFullYear() + '-' +
        (d2e.getMonth() + 1) + '-' +
        d2e.getDate());

      data.froms.sort();
      data.lists.sort();
      data.emails.sort();
      data.subjects.sort();

      Mailpile.API.with_template('modal-related-search', function(modal) {
        Mailpile.UI.show_modal(modal(data));
      });
    });
  }
};


Mailpile.DELETEMEshow_message_hints = function($context, selected) {
  $.each(selected, function(key, mid) {
    if (mid != '!all') {
      var $elem = $context.find('.pile-message-' + mid);
      var hint = $elem.data('context-hint');
      if (hint) {
        var icon = $elem.data('context-icon');
        var url = $elem.data('context-url');
        var html = '';
        if (icon) html += '<span class="icon icon-' + icon + '"></span> ';
        html += hint;
        if (url) html = '<a href="' + url + '">' + html + '</a>';
        $('div.bulk-actions-hints').html(html);
      }
    }
  });
};


Mailpile.select_all_matches = function(elem) {
  if (!elem) elem = '.pile-results a';
  $(elem).closest('.selection-context')
         .find('#pile-select-all-action').val('!all');
  Mailpile.bulk_actions_update_ui();
  return false;
};


Mailpile.unselect_all_matches = function(elem) {
  if (!elem) elem = '.pile-results a';
  $(elem).closest('.selection-context')
         .find('#pile-select-all-action').val('');
  Mailpile.bulk_actions_update_ui();
  return false;
};


Mailpile.bulk_action_read = function(elem, callback) {
  var $context = Mailpile.UI.Selection.context(elem || '.pile-results');
  Mailpile.UI.Tagging.tag_and_update_ui({
    del: 'new',
    mid: Mailpile.UI.Selection.selected($context),
    context: $context.find('.search-context').data('context')
  }, 'read', callback);
};


Mailpile.bulk_action_unread = function(elem, callback) {
  var $context = Mailpile.UI.Selection.context(elem || '.pile-results');
  Mailpile.UI.Tagging.tag_and_update_ui({
    add: 'new',
    mid: Mailpile.UI.Selection.selected($context),
    context: $context.find('.search-context').data('context')
  }, 'unread', callback);
};


Mailpile.bulk_action_select_target = function() {
  var target = this.search_target;
  var $tr = $('.pile-message').eq(target);
  $tr.addClass('result-on').find('input[type=checkbox]').prop('checked', true);
  this.bulk_actions_update_ui();
  return true;
};


Mailpile.bulk_action_deselect_target = function() {
  var target = this.search_target;
  var $tr = $('.pile-message').eq(target);
  $tr.removeClass('result-on')
     .find('input[type=checkbox]').prop('checked', false);
  this.bulk_actions_update_ui();
  return true;
};

Mailpile.bulk_action_select_all = function() {
  var checkboxes = $('.pile-results input[type=checkbox]');
  $.each(checkboxes, function() {
    Mailpile.pile_action_select($(this).parent().parent());
  });
  $("#pile-select-all-action").prop('checked', true);
  Mailpile.bulk_actions_update_ui();
};


Mailpile.bulk_action_select_none = function() {
  var checkboxes = $('.pile-results input[type=checkbox]');
  $.each(checkboxes, function() {
    Mailpile.pile_action_unselect($(this).parent().parent());
  });
  $("#pile-select-all-action").prop('checked', false).val('');
  Mailpile.bulk_actions_update_ui();
};


Mailpile.bulk_action_select_invert = function() {
  var checkboxes = $('.pile-results input[type=checkbox]');
  $.each(checkboxes, function() {
    if ($(this).is(":checked")) {
      Mailpile.pile_action_unselect($(this).parent().parent(), 'partial');
    } else {
      Mailpile.pile_action_select($(this).parent().parent(), 'partial');
    }
  });
  Mailpile.bulk_actions_update_ui();
};

Mailpile.bulk_action_move_selection = function(keep, mover) {
  var checkboxes = $('.pile-results input[type=checkbox]');
  var selected = Mailpile.UI.Selection.selected(checkboxes.eq(0));
  if (selected.length == 0) {
    var $elem = $(checkboxes[0]).parent().parent();
    Mailpile.pile_action_select($elem);
    return $elem;
  }

  var $last = [];
  $.each(checkboxes, function() {
    var $e = $(this);
    if ($e.is(":checked")) $last = $e.parent().parent();
  });
  if ($last.length > 0) {
    var $next = $(mover($last));
    if (keep !== 'keep') Mailpile.pile_action_unselect($last);
    if ($next) Mailpile.pile_action_select($next);
    Mailpile.bulk_actions_update_ui();
    return $next;
  }
  return $last;
};

Mailpile.bulk_action_selection_up = function(keep) {
  return Mailpile.bulk_action_move_selection(keep, function($elem) {
    return $elem.prev();
  });
};

Mailpile.bulk_action_selection_down = function(keep) {
  return Mailpile.bulk_action_move_selection(keep, function($elem) {
    return $elem.next();
  });
};

Mailpile.open_or_close_selected_thread = function() {
  var selected = Mailpile.UI.Selection.selected('.pile-results');
  var msg = [];
  if (selected.length === 1 && selected[0] == '!all') {
    msg = $(".pile-results .pile-message");
  }
  else {
    if (selected.length < 1) {
      Mailpile.pile_action_select($('.pile-results .pile-message').eq(0));
      selected = Mailpile.UI.Selection.selected('.pile-results');
    }
    if ((selected.length > 0) && (selected[0] != '!all')) {
      msg = $(".pile-results .pile-message-" + selected[selected.length - 1]);
    }
  }
  if (msg.length) {
    var $close = msg.eq(0).find('#close-message');
    if ($close.length == 0) {
      msg.eq(0).find(".subject a").trigger('click');
    }
    else {
      $('#close-message').trigger('click');
    }
  }
};
