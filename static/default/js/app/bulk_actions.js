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


/* Bulk Action - Tag */
$(document).on('click', '.bulk-action-tag', function() {
  mailpile.render_modal_tags();
});


/* Bulk Action - Archive */
$(document).on('click', '.bulk-action-archive', function() {
  mailpile.tag_add_delete('', 'inbox', mailpile.messages_cache, function() {

    // Update Pile View
    $.each(mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).fadeOut('fast');
    });

    // Empty Bulk Cache
    mailpile.messages_cache = [];

    // Update Bulk UI
    mailpile.bulk_actions_update_ui();
  });
});


/* Bulk Action - Trash */
$(document).on('click', '.bulk-action-trash', function() {
  mailpile.tag_add_delete('trash', 'new', mailpile.messages_cache, function() {

    // Update Pile View
    $.each(mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).fadeOut('fast');
    });

    // Empty Bulk Cache
    mailpile.messages_cache = [];

    // Update Bulk UI
    mailpile.bulk_actions_update_ui();
  });
});


/* Bulk Action - Spam */
$(document).on('click', '.bulk-action-spam', function() {
  mailpile.tag_add_delete('spam', 'new', mailpile.messages_cache, function() {

    // Update Pile View
    $.each(mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).fadeOut('fast');
    });

    // Empty Bulk Cache
    mailpile.messages_cache = [];

    // Update Bulk UI
    mailpile.bulk_actions_update_ui();
  });
});


/* Bulk Action - Mark Unread */
$(document).on('click', '.bulk-action-unread', function() {
  mailpile.bulk_action_unread();
});


/* Bulk Action - Mark Read */
$(document).on('click', '.bulk-action-read', function() {
  mailpile.bulk_action_read();    
});