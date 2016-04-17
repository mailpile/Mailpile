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
        if (selected.length == 1) Mailpile.show_message_hints($context, selected);
      }
      $context.find('#bulk-actions-message').html(message);

      var have_tags = {};
      for (var i = 0; i < selected.length; i++) {
        var tids = $context.find('.pile-message-' + selected[i])
                           .data('tids').split(/,/);
        for (var j = 0; j < tids.length; j++) have_tags[tids[j]] = true;
      }
      console.log(JSON.stringify(have_tags));

      Mailpile.show_bulk_actions($context.find('.bulk-actions').find('li'),
                                 have_tags);
    }
    else {
      var message = $context.find('#bulk-actions-message').data('bulk_selected_none');
      $context.find('#bulk-actions-message').html(message);
      Mailpile.hide_bulk_actions($context.find('.bulk-actions').find('li.hide'));
    }
  });
};


Mailpile.hide_message_hints = function($context) {
  $context.find('div.bulk-actions-hints').html('');
};


Mailpile.show_message_hints = function($context, selected) {
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
  $(elem).closest('.selection-context')
         .find('#pile-select-all-action').val('!all');
  Mailpile.bulk_actions_update_ui();
  return false;
};


Mailpile.unselect_all_matches = function(elem) {
  $(elem).closest('.selection-context')
         .find('#pile-select-all-action').val('');
  Mailpile.bulk_actions_update_ui();
  return false;
};


Mailpile.bulk_action_read = function(elem) {
  var $context = Mailpile.UI.Selection.context(elem || '.pile-results');
  Mailpile.UI.Tagging.tag_and_update_ui({
    del: 'new',
    mid: Mailpile.UI.Selection.selected($context),
    context: $context.find('.search-context').data('context')
  }, 'read');
};


Mailpile.bulk_action_unread = function(elem) {
  var $context = Mailpile.UI.Selection.context(elem || '.pile-results');
  Mailpile.UI.Tagging.tag_and_update_ui({
    add: 'new',
    mid: Mailpile.UI.Selection.selected($context),
    context: $context.find('.search-context').data('context')
  }, 'unread');
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


Mailpile.bulk_action_toggle_target = function() {
  var target = this.search_target;
  var $tr = $('.pile-message').eq((target === 'none') ? 0 : target);
  if ($tr.find('input[type=checkbox]').is(':checked')) {
    Mailpile.pile_action_unselect($tr);
  }
  else {
    Mailpile.pile_action_select($tr);
  }
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


Mailpile.bulk_action_select_between = function() {
  alert('FIXME: Will select messages between two points');
};


Mailpile.bulk_action_selection_up = function() {
  var checkboxes = $('.pile-results input[type=checkbox]');
  var selected = Mailpile.UI.Selection.selected(checkboxes.eq(0));
  if (selected.length == 0) {
    Mailpile.pile_action_select($(checkboxes[checkboxes.length-1]).parent().parent());
    return;
  }
  $.each(checkboxes, function() {
    if ($(this).parent().parent().next().children().children("input").is(":checked")) {
      Mailpile.pile_action_select($(this).parent().parent(), 'partial');
    } else {
      Mailpile.pile_action_unselect($(this).parent().parent(), 'partial');
    }
  });
  Mailpile.bulk_actions_update_ui();
};


Mailpile.bulk_action_selection_down = function() {
  var checkboxes = $('.pile-results input[type=checkbox]');
  var selected = Mailpile.UI.Selection.selected(checkboxes.eq(0));
  if (selected.length == 0) {
    Mailpile.pile_action_select($(checkboxes[0]).parent().parent());
    return;
  }
  $(checkboxes.get().reverse()).each(function() {
    if ($(this).parent().parent().prev().children().children("input").is(":checked")) {
      Mailpile.pile_action_select($(this).parent().parent());
    } else {
      Mailpile.pile_action_unselect($(this).parent().parent());
    }
  });
};


Mailpile.open_selected_thread = function() {
  var selected = Mailpile.UI.Selection.selected('.pile-results');
  if (Mailpile.search_target !== 'none') {
    var target = this['search_target'];
    $('.pile-results tr').eq(target).find('.subject a').eq(0).trigger('click');
  }
  else if (selected.length === 1 && selected[0] != '!all') {
    $(".pile-results .pile-message-" + selected[0]).eq(0)
      .find('.subject a').eq(0).trigger('click');
  }
};
