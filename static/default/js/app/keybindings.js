MailPile.prototype.keybinding_move_message = function(add_tag) {

  // Has Messages
  if (this.messages_cache.length) {

    var delete_tag = '';
    if ($.url(location.href).segment(1) === 'in') {
      delete_tag = $.url(location.href).segment(2);
    }

    // Add / Delete
    mailpile.tag_add_delete(add_tag, delete_tag, mailpile.messages_cache, function() {

      // Update Pile View
      $.each(mailpile.messages_cache, function(key, mid) {
        $('#pile-message-' + mid).fadeOut('fast');
      });

      // Empty Bulk Cache
      mailpile.messages_cache = [];

      // Update Bulk UI
      mailpile.bulk_actions_update_ui();
    });    
  }
  else {
    console.log('FIXME: Provide helpful / unobstrusive UI feedback that tells a user they hit a keybinding, then fades away');
  }
};