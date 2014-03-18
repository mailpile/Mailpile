/* Pile - Bulk Action Link */
$(document).on('click', '.bulk-action-tag', '.bulk-action-untag', function(e) {

  // Open Modal with selection options
  mailpile.tag_list(function(result) {

    var tags_html = '';
    var archive_html = '';

    $.each(result.tags, function(key, value) {
      if (value.display === 'tag') {
        tags_html += '<li class="checkbox-item-picker" data-tid="' + value.tid + '" data-slug="' + value.slug + '"><input type="checkbox"> ' + value.name + '</li>';          
      }
      else if (value.display === 'archive') {
        archive_html += '<li class="checkbox-item-picker"><input type="checkbox"> ' + value.name + '</li>';
      }
    });

    var modal_html = $("#modal-tag-picker").html();
    $('#modal-full').html(_.template(modal_html, { tags: tags_html, archive: archive_html }));
    $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
  });
});


$(document).on('click', '.bulk-action-later, .bulk-action-archive, .bulk-action-trash', function(e) {

	e.preventDefault();
	var action = $(this).attr('class').replace('bulk-action-', '')
  var delete_tag = '';

  if ($.url.segment(0) === 'in') {
   delete_tag = $.url.segment(1);
  }

  // Add / Delete
  mailpile.tag_add_delete(action, delete_tag, mailpile.bulk_cache, function() {

    // Update Pile View
    $.each(mailpile.bulk_cache, function(key, mid) {
      $('#pile-message-' + mid).fadeOut('fast');
    });

    // Empty Bulk Cache
    mailpile.bulk_cache = [];
  });
});

$(document).on('click', '.bulk-action-add-to-group', function(e) {

  var modal_html = $("#modal-group-editor").html();
  $('#modal-full').html(_.template(modal_html, {}));
  $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
});

// Mark Unread
$(document).on('click', '.bulk-action-unread', function() {
    mailpile.tag_add_delete('new', mailpile.tags_cache, mailpile.messages_cache, function(result) {

      // Empty Bulk Cache
      mailpile.bulk_cache = [];
    });
});

// Mark Read
$(document).on('click', '.bulk-action-read', function() {
    mailpile.tag_add_delete(mailpile.tags_cache, 'new', mailpile.messages_cache, function(result) {

      // Empty Bulk Cache
      mailpile.bulk_cache = [];
    });
});