MailPile.prototype.bulk_actions_update_ui = function() {
  if (mailpile.messages_cache.length === 1) {
    var message = '<span id="bulk-actions-selected-count">1</span> ' + $('#bulk-actions-message').data('bulk_selected');
    $('#bulk-actions-message').html(message);
    mailpile.show_bulk_actions($('.bulk-actions').find('li.hide'));
  }
  else if (mailpile.messages_cache.length < 1) { 
    var message = $('#bulk-actions-message').data('bulk_selected_none');
    $('#bulk-actions-message').html(message);
    mailpile.hide_bulk_actions($('.bulk-actions').find('li.hide'));
	}
	else {
	  $('#bulk-actions-selected-count').html(mailpile.messages_cache.length);
  }
};


MailPile.prototype.bulk_action_read = function() {
  this.tag_add_delete(mailpile.tags_cache, 'new', mailpile.messages_cache, function(result) {
    $.each(mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).removeClass('in_new');
    });
  });
};


MailPile.prototype.bulk_action_unread = function() {
  this.tag_add_delete('new', mailpile.tags_cache, mailpile.messages_cache, function(result) {
    $.each(mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).addClass('in_new');
    });
  });
};


MailPile.prototype.bulk_action_select_all = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  $.each(checkboxes, function() {      
    mailpile.pile_action_select($(this).parent().parent());
  });
  $("#pile-select-all-action").attr('checked','checked');
};


MailPile.prototype.bulk_action_select_none = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  $.each(checkboxes, function() {
    mailpile.pile_action_unselect($(this).parent().parent());
  });
  $("#pile-select-all-action").removeAttr('checked');
};


MailPile.prototype.bulk_action_select_invert = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  $.each(checkboxes, function() {
    if ($(this).is(":checked")) {
      mailpile.pile_action_unselect($(this).parent().parent());
    } else {
      mailpile.pile_action_select($(this).parent().parent());
    }
  });
  if (this['messages_cache'].length == checkboxes.length) {
    $("#pile-select-all-action").attr('checked','checked');
  } else if (this['messages_cache'].length == 0) {
    $("#pile-select-all-action").removeAttr('checked');
  }
};


MailPile.prototype.bulk_action_selection_up = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  if (this['messages_cache'].length == 0) {
    mailpile.pile_action_select($(checkboxes[checkboxes.length-1]).parent().parent());
    return;
  }
  $.each(checkboxes, function() {
    if ($(this).parent().parent().next().children().children("input").is(":checked")) {
      mailpile.pile_action_select($(this).parent().parent());
    } else {
      mailpile.pile_action_unselect($(this).parent().parent());
    }
  });
};


MailPile.prototype.bulk_action_selection_down = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  if (this['messages_cache'].length == 0) {
    mailpile.pile_action_select($(checkboxes[0]).parent().parent());
    return;
  }

  $(checkboxes.get().reverse()).each(function() {
    if ($(this).parent().parent().prev().children().children("input").is(":checked")) {
      mailpile.pile_action_select($(this).parent().parent());
    } else {
      mailpile.pile_action_unselect($(this).parent().parent());
    }
  });
};


MailPile.prototype.open_selected_thread = function() {
  if (this['messages_cache'].length == 1) {
    $("#pile-results input[type=checkbox]:checked").each(function() {
      window.location.href = $(this).parent().parent()
                                    .children(".subject")
                                    .children("a").attr("href");
    });
  }
};