/* Modals - Composer */

Mailpile.UI.Modals.ComposerEncryptionHelper = function(unencryptables) {

  var searching_template = _.template($('#modal-composer-encryption-helper').html());
  var searching_html = searching_template({ unencryptables: unencryptables });
  $('#modal-full').html(searching_html);

  // Show Modal
  $('#modal-full').modal(Mailpile.UI.ModalOptions);

};
