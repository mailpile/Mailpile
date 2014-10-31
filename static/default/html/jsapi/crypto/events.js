/* Crypto - Events */

/* Crypto - Import Key */
$(document).on('click', '.crypto-key-import', function(e) {
  e.preventDefault();
  var key_data = _.findWhere(Mailpile.crypto_keylookup, {fingerprints: $(this).data('fingerprint')});
  Mailpile.API.crypto_keyimport_post(key_data, function(result) {
    $('#modal-full').modal('hide');
  });
});


/* Crypto - Key Use */
$(document).on('change', '.crypto-key-policy', function() {
  
  alert('Change Key Policy to: ' + $(this).val() + ' for fingerprint: ' + $(this).data('fingerprint'));

});


$(document).on('click', '.crypto-searchkey-address', function(e) {
  e.preventDefault();

  alert()

});