/* Search - Options for sidebar */
MailPile.prototype.sidebar_tags_droppable_opts = {
  accept: 'td.draggable',
  activeClass: 'sidebar-tags-draggable-hover',
  hoverClass: 'sidebar-tags-draggable-active',
  tolerance: 'pointer',
  over: function(event, ui) {
    var tid = $(this).find('a').data('tid');
    setTimeout(function() {
      //mailpile.ui_sidebar_toggle_subtags(tid, 'open');
    }, 500);
  },
  out: function(event, ui) {
    var tid = $(this).find('a').data('tid');
    setTimeout(function() {
      //mailpile.ui_sidebar_toggle_subtags(tid, 'close');
    }, 1000);
  },
  drop: function(event, ui) {

    var tid = $(this).find('a').data('tid');

    // Add MID to Cache
    mailpile.bulk_cache_add('messages_cache', ui.draggable.parent().data('mid'));

    // Add / Delete
    mailpile.tag_add_delete(tid, mailpile.instance.search_tag_ids, mailpile.messages_cache, function() {

      // Update Pile View
      $.each(mailpile.messages_cache, function(key, mid) {
        $('#pile-message-' + mid).fadeOut('fast');
      });

      // Empty Bulk Cache
      mailpile.messages_cache = [];

      // Update Bulk UI
      mailpile.bulk_actions_update_ui();

      // Hide Collapsible
      mailpile.ui_sidebar_toggle_subtags(tid, 'close');
    });
  }
};


/* Search - Make search items draggable to sidebar */
$('li.sidebar-tags-draggable').droppable(mailpile.sidebar_tags_droppable_opts);