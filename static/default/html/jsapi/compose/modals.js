/* Modals - Composer */

Mailpile.UI.Modals.ComposerEncryptionHelper = function(mid, determine) {
  Mailpile.API.with_template('modal-composer-encryption-helper', function(modal) {
    determine['mid'] = mid;
    Mailpile.UI.show_modal(modal(determine));
  });
};
