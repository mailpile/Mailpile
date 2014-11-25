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
  Mailpile.API.tag_post({ del: 'inbox', mid: Mailpile.messages_cache}, function(result) {

    // Notifications
    Mailpile.notification(result);

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
$(document).on('click', '.bulk-action-trash', function(result) {
  Mailpile.API.tag_post({ add: 'trash', del: 'new', mid: Mailpile.messages_cache}, function(result) {

    // Notifications
    Mailpile.notification(result);

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
  Mailpile.API.tag_post({ add: 'spam', del: 'new', mid: Mailpile.messages_cache}, function(result) {

    // Notifications
    Mailpile.notification(result);

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

  var add_tags    = [];
  var remove_tags = [];
  var tag_data    = { mid: Mailpile.messages_cache };

  // Add Selection
  console.log(Mailpile.tags_cache);
  _.each($(this).find('input.tag-picker-checkbox'), function(val, key) {
    console.log($(val).val() + ' ---> ' + $(val).is(':checked') + ' ---> ' + _.indexOf(Mailpile.tags_cache, $(val).val()));
    if ($(val).is(':checked') && _.indexOf(Mailpile.tags_cache, $(val).val()) === -1) {
      console.log('adding to tags_cache ' + $(val).val());
      Mailpile.tags_cache.push($(val).val());
    }
  });

  console.log(Mailpile.tags_cache);

  // Make Data Struc
  if (action == 'add') {
    tag_data = _.extend(tag_data, { add: Mailpile.tags_cache });
  }
  else if (action === 'remove') {
    tag_data = _.extend(tag_data, { del: Mailpile.tags_cache });
  }

  // Send Result
  Mailpile.API.tag_post(tag_data, function(result) {

    // Notifications
    Mailpile.notification(result);

    // Add Tags to UI
    if (result.status === 'success') {

      var tag_link_template = _.template($('#template-search-tags-link').html());

      // Affected MID's
      _.each(result.result.msg_ids, function(mid, key) {

        // Select to minimize load traversing DOM
        $item = $('#pile-message-' + mid).find('td.subject span.item-tags');

        // Add / Remove Tags from UI
        if (action == 'add') {
          _.each(Mailpile.tags_cache, function(tid, key) {
            if ($('#pile-message-tag-' + tid + '-' + mid).length < 1) {
              var tag = _.findWhere(Mailpile.instance.tags, { tid: tid });
              tag['mid'] = mid;
              $item.append(tag_link_template(tag));
            }
          });
        }
        else if (action === 'remove') {
          _.each(Mailpile.tags_cache, function(tid, key) {
            if ($('#pile-message-tag-' + tid + '-' + mid).length >= 1) {
              $('#pile-message-tag-' + tid + '-' + mid).remove();
            };
          });
        }
      });
    }

    // Hide Modal
    $('#modal-full').modal('hide');
  });
});


$(document).on('click', '.tag-picker-checkbox', function(e) {
//  Mailpile.tags_cache = _.without(Mailpile.tags_cache, $(this).val());
});

