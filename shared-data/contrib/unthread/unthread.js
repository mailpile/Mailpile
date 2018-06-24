/* Mailpile.plugins.unthread */

function _message_click_handler(e) {
  e.preventDefault();
  var mid = $(this).closest('.has-mid').data('mid');
  Mailpile.auto_modal({
    method: 'GET',
    url: Mailpile.API.U('/message/unthread/=' + mid + '/modal.html'),
  });
}

function _modal_submit_handler(e) {
  e.preventDefault();
  var $form = $(this).closest('form');

  var mid = $form.find('input[name=mid]').val();
  var args = {mid: mid};

  var subject = $form.find('input[name=subject]').val();
  if (subject) args['subject'] = subject;

  Mailpile.API.message_unthread_post(args, function(result) {
    Mailpile.UI.hide_modal();
    Mailpile.go(Mailpile.urls.thread + mid + '/');
  });
};

$(document).on('click', '.message-action-unthread', _message_click_handler);
$(document).on('click', '.submit-modal-unthread', _modal_submit_handler);

return {
  'message_click_handler': _message_click_handler,
  'modal_submit_handler': _modal_submit_handler,
}
