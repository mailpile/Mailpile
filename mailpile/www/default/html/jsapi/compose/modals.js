/* Modals - Composer */

Mailpile.UI.Modals.ComposerEncryptionHelper = function(mid, determine) {

  determine['mid'] = mid;
  var searching_template = _.template($('#modal-composer-encryption-helper').html());
  var searching_html = searching_template(determine);
  $('#modal-full').html(searching_html);

  // Show Modal
  $('#modal-full').modal(Mailpile.UI.ModalOptions);

};