/* Thread - Show People In Conversation */
$(document).on('click', '.show-thread-people', function() {
 $('#modal-full .modal-title').html($('#thread-people').data('modal_title'));
 $('#modal-full .modal-body').html($('#thread-people').html());
 $('#modal-full').modal(Mailpile.UI.ModalOptions);
});


/* Thread - Show Tags In Converstation */
$(document).on('click', '.show-thread-tags', function() {
 $('#modal-full .modal-title').html($('#thread-tags').data('modal_title'));
 $('#modal-full .modal-body').html($('#thread-tags').html());
 $('#modal-full').modal(Mailpile.UI.ModalOptions);
});


/* Thread - Show Metadata Info */
$(document).on('click', '.thread-message-metadata-details-toggle', function() {
  var mid = $(this).data('mid');
  var target = '#metadata-details-' + mid;
  if ($(target).css('display') === 'none') {
    $(target).show('fast').addClass('border-bottom');
    $(this).css('color', '#4d4d4d');
  }
  else {
    $(target).hide('fast').removeClass('border-bottom');
    $(this).css('color', '#ccc');
  }
});


/* Thread - Expand Snippet */
$(document).on('click', 'div.thread-snippet', function(e) {  
  var mid = $(this).data('mid');
  if (e.target.href === undefined && $(e.target).data('expand') !== 'no' && $(e.target).hasClass('show-thread-message-metadata-details') === false) {
    Mailpile.UI.Message.ShowMessage(mid);
  }
});


/* Thread - Message Quote */
$(document).on('click', '.thread-message-actions-quote', function() {
  var mid = $(this).parent().parent().data('mid');
  $('#message-' + mid).find('.thread-item-quote').removeClass('hide');
  $('#message-' + mid).find('.thread-item-signature').removeClass('hide');
  $(this).parent().hide();
});


/* Thread - Might Move to Global Location / Abstraction */
$(document).on('click', '.dropdown-toggle', function() {
  $(this).find('.icon-arrow-right').removeClass('icon-arrow-right').addClass('icon-arrow-down');
});
