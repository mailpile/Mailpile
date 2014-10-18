/* Composer - Crypto */

Mailpile.Composer.Crypto.load_states = function() {

  var state = $('#compose-crypto').val();
  var signature = 'none';
  var encryption = 'none';

  if (state.match(/sign/)) {
    signature = 'sign';
  }
  if (state.match(/encrypt/)) {
    encryption = 'encrypt';
  }

  Mailpile.Composer.Crypto.signature_toggle(signature);
  Mailpile.Composer.Crypto.encryption_toggle(encryption);
};


/* Compose - Set crypto state of message */
Mailpile.Composer.Crypto.set_state = function() {
  
  // Returns: none, openpgp-sign, openpgp-encrypt and openpgp-sign-encrypt
  var state = 'none';
  var signature = $('#compose-signature').val();
  var encryption = $('#compose-encryption').val();

  if (signature == 'sign' && encryption == 'encrypt') {
    state = 'openpgp-sign-encrypt'; 
  }
  else if (signature == 'sign') {
    state = 'openpgp-sign';
  }
  else if (encryption == 'encrypt') {
    state = 'openpgp-encrypt';
  }
  else {
    state = 'none';
  }

  $('#compose-crypto').val(state);

  return state;
};


/* Compose - Determine possible crypto "signature" of a message */
Mailpile.Composer.Crypto.determine_signature = function() {

  if ($('#compose-signature').val() === '') {
    if ($.inArray($('#compose-pgp').val(), ['openpgp-sign', 'openpgp-sign-encrypt']) > -1) {
      var status = 'sign';
    } else {
      var status = 'none';
    }
  } else {
    var status = $('#compose-signature').val();
  }

  return status;
};


/* Compose - Determine possible crypto "encryption" of a message */
Mailpile.Composer.Crypto.determine_encryption = function(mid, contact) {

  var status = 'none';
  var addresses  = $('#compose-to-' + mid).val() + ', ' + $('#compose-cc-' + mid).val() + ', ' + $('#compose-bcc-' + mid).val();
  var recipients = addresses.split(/, */);

  if (contact) {
    recipients.push(contact);
  }

  var count_total = 0;
  var count_secure = 0;
    
  $.each(recipients, function(key, value){  
    if (value) {
      count_total++;
      var check = Mailpile.Composer.Recipients.analyze_address(value);
      if (check.flags.secure) {
        count_secure++;
      }
    }
  });

  if (count_secure === count_total && count_secure !== 0) {
    status = 'encrypt';
  }
  else if (count_secure < count_total && count_secure > 0) {
    status = 'cannot';
  }

  return status;
};


/* Compose - Render crypto "signature" of a message */
Mailpile.Composer.Crypto.signature_toggle = function(status) {
  if (status === 'sign') {
    $('.compose-crypto-signature').data('crypto_color', 'crypto-color-green');  
    $('.compose-crypto-signature').attr('title', $('.compose-crypto-signature').data('crypto_title_signed'));
    $('.compose-crypto-signature span.icon').removeClass('icon-signature-none').addClass('icon-signature-verified');
    $('.compose-crypto-signature span.text').html($('.compose-crypto-signature').data('crypto_signed'));
    $('.compose-crypto-signature').removeClass('none').addClass('signed bounce');

  } else if (status === 'none') {
    $('.compose-crypto-signature').data('crypto_color', 'crypto-color-gray');  
    $('.compose-crypto-signature').attr('title', $('.compose-crypto-signature').data('crypto_title_not_signed'));
    $('.compose-crypto-signature span.icon').removeClass('icon-signature-verified').addClass('icon-signature-none');
    $('.compose-crypto-signature span.text').html($('.compose-crypto-signature').data('crypto_not_signed'));
    $('.compose-crypto-signature').removeClass('signed').addClass('none bounce');

  } else {
    $('.compose-crypto-signature').data('crypto_color', 'crypto-color-red');
    $('.compose-crypto-signature').attr('title', $('.compose-crypto-signature').data('crypto_title_signed_error'));
    $('.compose-crypto-signature span.icon').removeClass('icon-signature-none icon-signature-verified').addClass('icon-signature-error');
    $('.compose-crypto-signature span.text').html($('.compose-crypto-signature').data('crypto_signed_error'));
    $('.compose-crypto-signature').removeClass('none').addClass('error bounce');
  }

    // Set Form Value
  if ($('#compose-signature').val() !== status) {
    $('.compose-crypto-signature').addClass('bounce');
    $('#compose-signature').val(status);

    // Remove Animation
    setTimeout(function() {
      $('.compose-crypto-signature').removeClass('bounce');
    }, 1000);

    Mailpile.Composer.Crypto.set_state();
  }
};


/* Compose - Render crypto "encryption" of a message */
Mailpile.Composer.Crypto.encryption_toggle = function(status) {

  if (status == 'encrypt') {
    $('.compose-crypto-encryption').data('crypto_color', 'crypto-color-green');
    $('.compose-crypto-encryption').attr('title', $('.compose-crypto-encryption').data('crypto_title_encrypt'));
    $('.compose-crypto-encryption span.icon').removeClass('icon-lock-open').addClass('icon-lock-closed');
    $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_encrypt'));
    $('.compose-crypto-encryption').removeClass('none error cannot').addClass('encrypted');

  } else if (status === 'cannot') {
    $('.compose-crypto-encryption').data('crypto_color', 'crypto-color-orange');
    $('.compose-crypto-encryption').attr('title', $('.compose-crypto-encryption').data('crypto_title_cannot_encrypt'));
    $('.compose-crypto-encryption span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
    $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_cannot_encrypt'));
    $('.compose-crypto-encryption').removeClass('none encrypted error').addClass('cannot');

  } else if (status === 'none' || status == '') {
    $('.compose-crypto-encryption').data('crypto_color', 'crypto-color-gray');
    $('.compose-crypto-encryption').attr('title', $('.compose-crypto-encryption').data('crypto_title_none'));
    $('.compose-crypto-encryption span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
    $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_none'));
    $('.compose-crypto-encryption').removeClass('encrypted cannot error').addClass('none');

  } else {
    $('.compose-crypto-encryption').data('crypto_color', 'crypto-color-red');
    $('.compose-crypto-encryption').attr('title', $('.compose-crypto-encryption').data('crypto_title_encrypt_error'));
    $('.compose-crypto-encryption span.icon').removeClass('icon-lock-open icon-lock-closed').addClass('icon-lock-error');
    $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_cannot_encrypt'));
    $('.compose-crypto-encryption').removeClass('encrypted cannot none').addClass('error');
  }

  // Set Form Value
  if ($('#compose-encryption').val() !== status) {

    $('.compose-crypto-encryption').addClass('bounce');
    $('#compose-encryption').val(status);

    // Remove Animation
    setTimeout(function() {
      $('.compose-crypto-encryption').removeClass('bounce');
    }, 1000);
    
    Mailpile.Composer.Crypto.set_state();
  }
};