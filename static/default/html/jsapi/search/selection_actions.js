/* Search - Bulk Select / Unselect All */
$(document).on('click', '#pile-select-all-action', function(e) {

  var checkboxes = $('#pile-results input[type=checkbox]');

  if ($(this).attr('checked') === undefined) {
    $.each(checkboxes, function() {      
      Mailpile.pile_action_select($(this).parent().parent());
    });
    $(this).attr('checked','checked');

  } else {
    $.each(checkboxes, function() {
      Mailpile.pile_action_unselect($(this).parent().parent());
    });
    $(this).removeAttr('checked');
  }
});


/* Search - Bulk Action - Tag */
$(document).on('click', '.bulk-action-tag', function() {
  Mailpile.render_modal_tags();
});


/* Search - Bulk Action - Archive */
$(document).on('click', '.bulk-action-archive', function() {
  Mailpile.API.tag_post({ del: 'inbox', mid: Mailpile.messages_cache}, function() {

    // Update Pile View
    $.each(Mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).fadeOut('fast');
    });

    // Empty Bulk Cache
    Mailpile.messages_cache = [];

    // Update Bulk UI
    Mailpile.bulk_actions_update_ui();
  });
});


/* Search - Bulk Action - Trash */
$(document).on('click', '.bulk-action-trash', function() {
  Mailpile.API.tag_post({ add: 'trash', del: 'new', mid: Mailpile.messages_cache}, function() {

    // Update Pile View
    $.each(Mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).fadeOut('fast');
    });

    // Empty Bulk Cache
    Mailpile.messages_cache = [];

    // Update Bulk UI
    Mailpile.bulk_actions_update_ui();
  });
});


/* Search - Bulk Action - Spam */
$(document).on('click', '.bulk-action-spam', function() {
  Mailpile.API.tag_post({ add: 'spam', del: 'new', mid: Mailpile.messages_cache}, function() {

    // Update Pile View
    $.each(Mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).fadeOut('fast');
    });

    // Empty Bulk Cache
    Mailpile.messages_cache = [];

    // Update Bulk UI
    Mailpile.bulk_actions_update_ui();
  });
});


/* Search - Bulk Action - Mark Unread */
$(document).on('click', '.bulk-action-unread', function() {
  Mailpile.bulk_action_unread();
});


/* Search - Bulk Action - Mark Read */
$(document).on('click', '.bulk-action-read', function() {
  Mailpile.bulk_action_read();    
});


/* Search - Submit multi tag/untag on search selection */
$(document).on('submit', '#form-tag-picker', function(e) {

  e.preventDefault();
  var action = $("button:focus").data('action');

  var add_tags = []
  var remove_tags = []
  if (action == 'add') { 
    add_tags = Mailpile.tags_cache;
  }
  else if (action === 'remove') {
    remove_tags = Mailpile.tags_cache
  }

  // Send Result
   Mailpile.API.tag_post({ add: add_tags, del: remove_tags, mid: Mailpile.messages_cache}, function(result) {
    var tag_link_template = $('#template-search-pile-tags-link').html();

    $.each(result.msg_ids, function(key, mid) {

      // Assign selector to minimize load on traversing DOM
      $item = $('#pile-message-' + mid + ' td.subject span.item-tags'); 

      // Add Icon
      if ($item.find('span.icon-tag').length < 1) {
        $item.html('<span class="icon-tag"></span>');
      }

      // Add Tags
      $.each(result.tagged, function(key, tag) {
        tag.mid = mid;
        $item.append(_.template(tag_link_template, tag));
      });

      // Remove Tags
      $.each(result.untagged, function(key, untag) {
        console.log('performing UNTAG on: ' + untag);
 //       if ($('#pile-message-tag-' + mid + '-' + tid).length) {
 //         $('#pile-message-tag-' + mid + '-' + tid).remove();
 //       };
      });
    });

    // Clean Caches and hide Modal
    Mailpile.messages_cache = [];
    Mailpile.tags_cache = [];
    $('#modal-full').modal('hide');
  });
});