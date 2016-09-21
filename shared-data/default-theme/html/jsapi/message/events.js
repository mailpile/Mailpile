/* Thread - Show People In Conversation */
$(document).on('click', '.show-thread-people', function() {
  // FIXME: Old/unreliable modal code
  $('#modal-full .modal-title').html($('#thread-people').data('modal_title'));
  $('#modal-full .modal-body').html($('#thread-people').html());
  $('#modal-full').modal(Mailpile.UI.modal_options);
});


/* Thread - Show Tags In Converstation */
$(document).on('click', '.show-thread-tags', function() {
  // FIXME: Old/unreliable modal code
  $('#modal-full .modal-title').html($('#thread-tags').data('modal_title'));
  $('#modal-full .modal-body').html($('#thread-tags').html());
  $('#modal-full').modal(Mailpile.UI.modal_options);
});


/* Thread - Show Metadata Info */
$(document).on('click', '.message-metadata-details-toggle', function() {
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
  if (e.target.href === undefined && $(e.target).data('expand') !== 'no' && $(e.target).hasClass('show-message-metadata-details') === false) {
    Mailpile.UI.Message.ShowMessage(mid);
  }
});


/* Thread - Message Quote */
$(document).on('click', '.message-actions-quote', function() {
  var mid = $(this).parent().parent().data('mid');
  $('#message-' + mid).find('.message-part-quote').removeClass('hide');
  $('#message-' + mid).find('.message-part-signature').removeClass('hide');
  $(this).parent().hide();
});


/* Thread - Might Move to Global Location / Abstraction */
$(document).on('click', '.dropdown-toggle', function() {
  $(this).find('.icon-arrow-right').removeClass('icon-arrow-right').addClass('icon-arrow-down');
});


$(document).on('click', '.message-toggle-html', function(e) {
  var state = $(this).data('state');
  var mid = $(this).data('mid');
  if (state === 'plain') {
    $(this).data('state', 'html');
    $(this).html('{{_("Plain Text")|escapejs}}');
    Mailpile.Message.ShowHTML(mid);
  } else {
    $(this).data('state', 'plain');
    $(this).html('HTML');
    Mailpile.Message.ShowPlain(mid);
  }
});


$(document).on('click', '.message-show-html', function(e) {
  var mid = $(this).closest('.has-mid').data('mid');
  console.log('Should show message HTML parts for ' + mid);
  Mailpile.Message.ShowHTML(mid);
  return false;
});


$(document).on('click', '.message-show-text', function(e) {
  var mid = $(this).closest('.has-mid').data('mid');
  console.log('Should show message text parts ' + mid);
  Mailpile.Message.ShowPlain(mid);
  return false;
});
