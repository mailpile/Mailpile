/* Crypto - Events */

$(document).on('click', '.btn-crypto-search-key', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.CryptoFindKeys({
    query: ''
  });
});


$(document).on('click', '.btn-crypto-upload-key', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.CryptoUploadKey({});
});


/* Crypto - show / hide details */
$(document).on('click', '.searchkey-result-score', function(e) {
  var fingerprint = $(this).data('fingerprint');
  if ($('#item-encryption-key-' + fingerprint).find('.searchkey-result-details').css('display') == 'none') {
    $('#item-encryption-key-' + fingerprint).find('.searchkey-result-details').fadeIn();
  } else {
    $('#item-encryption-key-' + fingerprint).find('.searchkey-result-details').fadeOut();
  }
});


$(document).on('submit', '#form-search-keyservers', function(e) {
  e.preventDefault();
  
  // Hide Form
  $('#form-search-keyservers').removeClass('fadeIn').addClass('hide');

  // Query
  var query = $(this).find('input[type=text]').val();
  Mailpile.Crypto.Find.Keys({
    container: '#search-keyservers',
    action: 'hide-modal',
    query: query,
    complete: function() {
      $('#search-keyservers-again').removeClass('hide').addClass('fadeIn');      
    }
  });
});


$(document).on('click', '#btn-search-keyservers-again', function(e) {
  e.preventDefault();
  $('#search-keyservers-again').removeClass('fadeIn').addClass('hide');
  $('#search-keyservers').fadeOut().find('ul.result').html('');
  $('#form-search-keyservers').removeClass('hide').addClass('fadeIn')
    .find('input[type=text]').val('');
});


/* Crypto - import key */
$(document).on('click', '.crypto-key-import', function(e) {
  e.preventDefault();
  Mailpile.Crypto.Import.Key({ action: $(this).data('action'), fingerprint: $(this).data('fingerprint')});
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

