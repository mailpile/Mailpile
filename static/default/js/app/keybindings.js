MailPile.prototype.keybinding_delete = function() {

  // Has Messages
  if (this.messages_cache.length) {

    var delete_tag = '';
    if ($.url(location.href).segment(1) === 'in') {
      delete_tag = $.url(location.href).segment(2);
    }

    // Add / Delete
    mailpile.tag_add_delete('trash', delete_tag, mailpile.messages_cache, function() {

      // Update Pile View
      $.each(mailpile.messages_cache, function(key, mid) {
        $('#pile-message-' + mid).fadeOut('fast');
      });

      // Empty Bulk Cache
      mailpile.messages_cache = [];
    });    
  }
};