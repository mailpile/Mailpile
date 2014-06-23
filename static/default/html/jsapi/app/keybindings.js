Mailpile.keybinding_move_message = function(add_tag) {

  // Has Messages
  if (this.messages_cache.length) {

    var delete_tags = Mailpile.instance.search_tag_ids;
    delete_tags.push('new');

    // Add / Delete
    Mailpile.tag_add_delete(add_tag, delete_tags, Mailpile.messages_cache, function() {

      // Update Pile View
      $.each(Mailpile.messages_cache, function(key, mid) {
        $('#pile-message-' + mid).fadeOut('fast');
      });

      // Empty Bulk Cache
      Mailpile.messages_cache = [];

      // Update Bulk UI
      Mailpile.bulk_actions_update_ui();
    });    
  }
  else {
    console.log('FIXME: Provide helpful / unobstrusive UI feedback that tells a user they hit a keybinding, then fades away');
  }
};