/* Search - Options for sidebar */
Mailpile.sidebar_tags_droppable_opts = {
//  accept: ['td.draggable', 'div.thread-draggable'],
  activeClass: 'sidebar-tags-draggable-hover',
  hoverClass: 'sidebar-tags-draggable-active',
  tolerance: 'pointer',
  over: function(event, ui) {
    var tid = $(this).find('a').data('tid');
    setTimeout(function() {
      //Mailpile.ui_sidebar_toggle_subtags(tid, 'open');
    }, 500);
  },
  out: function(event, ui) {
    var tid = $(this).find('a').data('tid');
    setTimeout(function() {
      //Mailpile.ui_sidebar_toggle_subtags(tid, 'close');
    }, 1000);
  },
  drop: function(event, ui) {

    var tid = $(this).find('a').data('tid');

    // Add MID to Cache
    Mailpile.bulk_cache_add('messages_cache', ui.draggable.parent().data('mid'));

    // Add / Delete
    if (Mailpile.instance.state.command_url == '/message/') {
      var tags_delete = ['inbox'];
    } else {
      var tags_delete = Mailpile.instance.search_tag_ids;
    }

    Mailpile.tag_add_delete(tid, tags_delete, Mailpile.messages_cache, function() {

      // Update Pile View
      if (Mailpile.instance.state.command_url == '/search/') {
        $.each(Mailpile.messages_cache, function(key, mid) {
          $('#pile-message-' + mid).fadeOut('fast');
        });
  
        // Empty Bulk Cache
        Mailpile.messages_cache = [];
  
        // Update Bulk UI
        Mailpile.bulk_actions_update_ui();
  
        // Hide Collapsible
        Mailpile.ui_sidebar_toggle_subtags(tid, 'close');

      } else {
        // FIXME: this action is up for discussion
        // Github Issue - https://github.com/pagekite/Mailpile/issues/794
        window.location.href = '/in/inbox/';
      }
    });
  }
};


/* Search - Make search items draggable to sidebar */
$('li.sidebar-tags-draggable').droppable(Mailpile.sidebar_tags_droppable_opts);