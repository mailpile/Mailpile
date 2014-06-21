MailPile.prototype.keybinding_move_message = function(add_tag) {

  // Has Messages
  if (this.messages_cache.length) {

    var delete_tags = mailpile.instance.search_tag_ids;
    delete_tags.push('new');

    // Add / Delete
    mailpile.tag_add_delete(add_tag, delete_tags, mailpile.messages_cache, function() {

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