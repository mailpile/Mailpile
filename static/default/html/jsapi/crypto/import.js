/* Crypto - Import */


Mailpile.Crypto.Import.Key = function(action, fingerprint) {

  var key_data = _.findWhere(Mailpile.crypto_keylookup, {fingerprints: fingerprint});

  // Lookup
  Mailpile.API.crypto_keyimport_post(key_data, function(result) {
    if (result.status === 'success' && action === 'hide-modal') {
      $('#modal-full').modal('hide');
    }
    else if (result.status === 'success' && action === 'hide-item') {
      // FIXME: kludgy
      $('#item-encryption-key-' + fingerprint).fadeOut();
    }
  });

};