/* Modals - Composer */

Mailpile.UI.Modals.ComposerEncryptionHelper = function(mid, determine) {
  Mailpile.API.with_template('modal-composer-encryption-helper', function(modal) {
    determine['mid'] = mid;
    $('#modal-full').html(modal(determine));
    $('#modal-full').modal(Mailpile.UI.ModalOptions);
  });
};
