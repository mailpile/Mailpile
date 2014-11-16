/* Crypto - Events */

/* Crypto - import key */
$(document).on('click', '.crypto-key-import', function(e) {
  e.preventDefault();
  Mailpile.Crypto.Import.Key($(this).data('action'), $(this).data('fingerprint'));
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