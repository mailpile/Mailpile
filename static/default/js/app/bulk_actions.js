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
  });
});


/* Bulk Action - Trash */
$(document).on('click', '.bulk-action-trash', function() {
  mailpile.tag_add_delete('trash', '', mailpile.messages_cache, function() {

    // Update Pile View
    $.each(mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).fadeOut('fast');
    });

    // Empty Bulk Cache
    mailpile.messages_cache = [];
  });
});


/* Bulk Action - Add to Group */
$(document).on('click', '.bulk-action-add-to-group', function() {
  var modal_html = $("#modal-group-editor").html();
  $('#modal-full').html(_.template(modal_html, {}));
  $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
});


/* Bulk Action - Mark Unread */
$(document).on('click', '.bulk-action-unread', function() {
    mailpile.tag_add_delete('new', mailpile.tags_cache, mailpile.messages_cache, function(result) {
      $.each(mailpile.messages_cache, function(key, mid) {
        $('#pile-message-' + mid).addClass('in_new');
      });
      // Empty Bulk Cache
      mailpile.bulk_cache = [];
    });
});


/* Bulk Action - Mark Read */
$(document).on('click', '.bulk-action-read', function() {
    mailpile.tag_add_delete(mailpile.tags_cache, 'new', mailpile.messages_cache, function(result) {
      $.each(mailpile.messages_cache, function(key, mid) {
        $('#pile-message-' + mid).removeClass('in_new');
      });
      // Empty Bulk Cache
      mailpile.bulk_cache = [];
    });
});