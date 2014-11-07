/* Crypto - Events */

/* Crypto - import key */
$(document).on('click', '.crypto-key-import', function(e) {
  e.preventDefault();
  var key_data = _.findWhere(Mailpile.crypto_keylookup, {fingerprints: $(this).data('fingerprint')});
  Mailpile.API.crypto_keyimport_post(key_data, function(result) {
    $('#modal-full').modal('hide');
  });
});


/* Crypto - key use */
$(document).on('change', '.crypto-key-policy', function() {
  
  alert('Change Key Policy to: ' + $(this).val() + ' for fingerprint: ' + $(this).data('fingerprint'));

});


/* Crypto - looks up keys based on a given email address */
$(document).on('click', '.crypto-searchkey-address', function(e) {
  e.preventDefault();
  var address = $(this).data('address');
  var target = $(this).data('target');
  
});