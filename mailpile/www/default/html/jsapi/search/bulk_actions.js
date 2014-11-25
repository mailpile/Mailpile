Mailpile.bulk_actions_update_ui = function() {
  if (Mailpile.messages_cache.length === 1) {
    var message = '<span id="bulk-actions-selected-count">1</span> ' + $('#bulk-actions-message').data('bulk_selected');
    $('#bulk-actions-message').html(message);
    Mailpile.show_bulk_actions($('.bulk-actions').find('li.hide'));
  }
  else if (Mailpile.messages_cache.length < 1) { 
    var message = $('#bulk-actions-message').data('bulk_selected_none');
    $('#bulk-actions-message').html(message);
    Mailpile.hide_bulk_actions($('.bulk-actions').find('li.hide'));
	}
	else {
	  $('#bulk-actions-selected-count').html(Mailpile.messages_cache.length);
  }
};


Mailpile.bulk_action_read = function() {
  Mailpile.API.tag_post({ del: 'new', mid: Mailpile.messages_cache }, function(result) {
    $.each(Mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).removeClass('in_new');
    });
  });
};


Mailpile.bulk_action_unread = function() {
  Mailpile.API.tag_post({ add: 'new', mid: Mailpile.messages_cache }, function(result) {
    $.each(Mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).addClass('in_new');
    });
  });
};


Mailpile.bulk_action_select_target = function() {
  var target = this.search_target;
  var mid = $('#pile-results tr').eq(target).data('mid');
  Mailpile.bulk_cache_add('messages_cache', mid);
  $('#pile-message-' + mid).addClass('result-on').find('input[type=checkbox]').prop('checked',true);
  this.bulk_actions_update_ui();
  return true;
};


Mailpile.bulk_action_deselect_target = function() {
  var target = this.search_target;
  var mid = $('#pile-results tr').eq(target).data('mid');
  Mailpile.bulk_cache_remove('messages_cache', mid);
  $('#pile-message-' + mid).removeClass('result-on').find('input[type=checkbox]').prop('checked', false);
  this.bulk_actions_update_ui();
  return true;
};


Mailpile.bulk_action_toggle_target = function() {
  var target = this.search_target;
  // No Target
  if (target === 'none') {
    var mid = $('#pile-results tr').eq(0).data('mid');
    if ($('#pile-message-' + mid).find('input[type=checkbox]').is(':checked')) {
      Mailpile.pile_action_unselect($('#pile-message-' + mid));
    } else {
      Mailpile.pile_action_select($('#pile-message-' + mid));
    }
  }
  // Has Target
  else {
    var mid = $('#pile-results tr').eq(target).data('mid');
    if ($('#pile-message-' + mid).find('input[type=checkbox]').is(':checked')) {
      Mailpile.bulk_action_deselect_target();
    } else {
      Mailpile.bulk_action_select_target();
    }
  }
  return true;
};


Mailpile.bulk_action_select_all = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  $.each(checkboxes, function() {      
    Mailpile.pile_action_select($(this).parent().parent());
  });
  $("#pile-select-all-action").attr('checked','checked');
};


Mailpile.bulk_action_select_none = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  $.each(checkboxes, function() {
    Mailpile.pile_action_unselect($(this).parent().parent());
  });
  $("#pile-select-all-action").removeAttr('checked');
};


Mailpile.bulk_action_select_invert = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  $.each(checkboxes, function() {
    if ($(this).is(":checked")) {
      Mailpile.pile_action_unselect($(this).parent().parent());
    } else {
      Mailpile.pile_action_select($(this).parent().parent());
    }
  });
  if (this['messages_cache'].length == checkboxes.length) {
    $("#pile-select-all-action").attr('checked','checked');
  } else if (this['messages_cache'].length == 0) {
    $("#pile-select-all-action").removeAttr('checked');
  }
};


Mailpile.bulk_action_select_between = function() {
  alert('FIXME: Will select messages between two points');
};


Mailpile.bulk_action_selection_up = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  if (this['messages_cache'].length == 0) {
    Mailpile.pile_action_select($(checkboxes[checkboxes.length-1]).parent().parent());
    return;
  }
  $.each(checkboxes, function() {
    if ($(this).parent().parent().next().children().children("input").is(":checked")) {
      Mailpile.pile_action_select($(this).parent().parent());
    } else {
      Mailpile.pile_action_unselect($(this).parent().parent());
    }
  });
};


Mailpile.bulk_action_selection_down = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  if (this['messages_cache'].length == 0) {
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
  if (this['messages_cache'].length == 1) {
    $("#pile-results input[type=checkbox]:checked").each(function() {
      window.location.href = $(this).parent().parent()
                                    .children(".subject")
                                    .children("a").attr("href");
    });
  }
};