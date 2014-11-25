/* Crypto - Import */


Mailpile.Crypto.Import.Key = function(action, fingerprint) {

  // Show Processing UI feedback
  var importing_template = _.template($('#template-crypto-encryption-key-importing').html());
  var importing_html     = importing_template({ action: action, fingerprint: fingerprint });
  $('#item-encryption-key-' + fingerprint).replaceWith(importing_html);

  // Lookup
  var key_data = _.findWhere(Mailpile.crypto_keylookup, {fingerprints: fingerprint});

  Mailpile.API.crypto_keyimport_post(key_data, function(result) {

    if (result.status === 'success') {

      for (var key in result.result) {
        if (result.result[key].fingerprint === fingerprint) {
          var key_result = result.result[key];

          // FIXME: kludgy
          key_result['avatar'] = '/static/img/avatar-default.png';
          key_result['uid'] = key_result.uids[0];
          key_result['action'] = 'hide-modal';
          key_result['on_keychain'] = true;
        }
      }

      var key_template = _.template($('#template-crypto-encryption-key').html());
      var key_html = key_template(key_result);

      $('#item-encryption-key-' + fingerprint).replaceWith(key_html);
    }
/*
    if (result.status === 'success' && action === 'hide-modal') {
      $('#modal-full').modal('hide');
    }
    else if (result.status === 'success' && action === 'hide-item') {
      // FIXME: kludgy
      $('#item-encryption-key-' + fingerprint).fadeOut();
    }
*/
  });

};