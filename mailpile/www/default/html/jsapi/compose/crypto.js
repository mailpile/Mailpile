/* Composer - Crypto */

Mailpile.Composer.Crypto.LoadStates = function(mid) {

  var state = $('#compose-crypto-' + mid).val();
  var signature = 'none';
  var encryption = 'none';
  var determine = Mailpile.Composer.Crypto.DetermineEncryption(mid, false);

  // Use signature
  if (state.match(/sign/)) {
    signature = 'sign';
  }

  // Use saved state or determine
  if (state.match(/encrypt/)) {
    encryption = 'encrypt';
  } else {
    encryption = determine.state;
  }

  Mailpile.Composer.Crypto.SignatureToggle(signature, mid);
  Mailpile.Composer.Crypto.EncryptionToggle(encryption, mid);
};


/* Compose - Set crypto state of message */
Mailpile.Composer.Crypto.SetState = function(mid) {
  
  // Returns: none, openpgp-sign, openpgp-encrypt and openpgp-sign-encrypt
  var state = 'none';
  var signature = $('#compose-signature-' + mid).val();
  var encryption = $('#compose-encryption-' + mid).val();

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

  $('#compose-crypto-' + mid).val(state);
  return state;
};


/* Compose - Determine possible crypto "signature" of a message */
Mailpile.Composer.Crypto.DetermineSignature = function(mid) {

  if ($('#compose-signature-' + mid).val() === '') {
    if ($.inArray($('#compose-pgp').val(), ['openpgp-sign', 'openpgp-sign-encrypt']) > -1) {
      var status = 'sign';
    } else {
      var status = 'none';
    }
  } else {
    var status = $('#compose-signature-' + mid).val();
  }

  return status;
};


/* Compose - Determine possible crypto "encryption" of a message */
Mailpile.Composer.Crypto.DetermineEncryption = function(mid, contact) {

  var state = 'none';
  var addresses  = $('#compose-to-' + mid).val() + ', ' + $('#compose-cc-' + mid).val() + ', ' + $('#compose-bcc-' + mid).val();
  var recipients = addresses.split(/, */);
  var unencryptables = [];    

  if (contact) {
    recipients.push(contact);
  }

  var count_total = 0;
  var count_secure = 0;
    
  $.each(recipients, function(key, value){  
    if (value) {
      count_total++;
      var check = Mailpile.Composer.Recipients.AnalyzeAddress(value);
      // console.log(check);
      if (check.flags.secure) {
        count_secure++;
      } else {
        unencryptables.push(check);
      }
    }
  });

  if (count_secure === count_total && count_secure !== 0) {
    state = 'encrypt';
  }
  else if (count_secure < count_total && count_secure > 0) {
    state = 'cannot';
  }

  return { state: state, unencryptables: unencryptables };
};


/* Compose - Render crypto "signature" of a message */
Mailpile.Composer.Crypto.SignatureToggle = function(status, mid) {

  if (status === 'sign') {
    $('#compose-crypto-signature-' + mid).data('crypto_color', 'crypto-color-green');
    $('#compose-crypto-signature-' + mid).attr('title', '{{_("This message will be verifiable to reicpients who have your encryption key. They will know it actually came from you :)")}}');
    $('#compose-crypto-signature-' + mid).find('span.icon').removeClass('icon-signature-none').addClass('icon-signature-verified');
    $('#compose-crypto-signature-' + mid).find('span.text').html('{{_("Verifiable")}}');
    $('#compose-crypto-signature-' + mid).removeClass('none').addClass('signed bounce');

  } else if (status === 'none') {
    $('#compose-crypto-signature-' + mid).data('crypto_color', 'crypto-color-gray');
    $('#compose-crypto-signature-' + mid).attr('title', '{{_("This message will not be verifiable, recipients will have no way of knowing it actually came from you.")}}');
    $('#compose-crypto-signature-' + mid).find('span.icon').removeClass('icon-signature-verified').addClass('icon-signature-none');
    $('#compose-crypto-signature-' + mid).find('span.text').html('{{_("Unverifiable")}}');
    $('#compose-crypto-signature-' + mid).removeClass('signed').addClass('none bounce');

  } else {
    $('#compose-crypto-signature-' + mid).data('crypto_color', 'crypto-color-red');
    $('#compose-crypto-signature-' + mid).attr('title', '{{_("Verification Error")}}');
    $('#compose-crypto-signature-' + mid).find('span.icon').removeClass('icon-signature-none icon-signature-verified').addClass('icon-signature-error');
    $('#compose-crypto-signature-' + mid).find('span.text').html('{{_("Error accesing your encryption key")}}');
    $('#compose-crypto-signature-' + mid).removeClass('none').addClass('error bounce');
  }

    // Set Form Value
  if ($('#compose-signature-' + mid).val() !== status) {
    $('#compose-crypto-signature-' + mid).addClass('bounce');
    $('#compose-signature-' + mid).val(status);

    // Remove Animation
    setTimeout(function() {
      $('#compose-crypto-signature-' + mid).removeClass('bounce');
    }, 1000);

    Mailpile.Composer.Crypto.SetState(mid);
  }
};


/* Compose - Render crypto "encryption" of a message */
Mailpile.Composer.Crypto.EncryptionToggle = function(status, mid) {

  if (status == 'encrypt') {
    $('#compose-crypto-encryption-' + mid).data('crypto_color', 'crypto-color-green');
    $('#compose-crypto-encryption-' + mid).attr('title', '{{_("This message and attachments will be encrypted. The recipients & subject (metadata) will not")}}');
    $('#compose-crypto-encryption-' + mid).find('span.icon').removeClass('icon-lock-open').addClass('icon-lock-closed');
    $('#compose-crypto-encryption-' + mid).find('span.text').html('{{_("Encrypted")}}');
    $('#compose-crypto-encryption-' + mid).removeClass('none error cannot').addClass('encrypted');

  } else if (status === 'cannot') {
    $('#compose-crypto-encryption-' + mid).data('crypto_color', 'crypto-color-orange');
    $('#compose-crypto-encryption-' + mid).attr('title', '{{_("This message cannot be encrypted because you do not have keys for one or more recipients")}}');
    $('#compose-crypto-encryption-' + mid).find('span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
    $('#compose-crypto-encryption-' + mid).find('span.text').html('{{_("Can Not Encrypt")}}');
    $('#compose-crypto-encryption-' + mid).removeClass('none encrypted error').addClass('cannot');

  } else if (status === 'none' || status == '') {
    $('#compose-crypto-encryption-' + mid).data('crypto_color', 'crypto-color-gray');
    $('#compose-crypto-encryption-' + mid).attr('title', '{{_("This message and metadata will not be encrypted")}}');
    $('#compose-crypto-encryption-' + mid).find('span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
    $('#compose-crypto-encryption-' + mid).find('span.text').html('{{_("None")}}');
    $('#compose-crypto-encryption-' + mid).removeClass('encrypted cannot error').addClass('none');

  } else {
    $('#compose-crypto-encryption-' + mid).data('crypto_color', 'crypto-color-red');
    $('#compose-crypto-encryption-' + mid).attr('title', '{{_("There was an error prepping this message for encryption")}}');
    $('#compose-crypto-encryption-' + mid).find('span.icon').removeClass('icon-lock-open icon-lock-closed').addClass('icon-lock-error');
    $('#compose-crypto-encryption-' + mid).find('span.text').html('{{_("Error Encrypting")}}');
    $('#compose-crypto-encryption-' + mid).removeClass('encrypted cannot none').addClass('error');
  }

  // Set Form Value
  if ($('#compose-encryption-' + mid).val() !== status) {
    $('#compose-crypto-encryption-' + mid).addClass('bounce');
    $('#compose-encryption-' + mid).val(status);

    // Remove Animation
    setTimeout(function() {
      $('#compose-crypto-encryption-' + mid).removeClass('bounce');
    }, 1000);
    
    Mailpile.Composer.Crypto.SetState(mid);
  }
};


Mailpile.Composer.Crypto.AttachKey = function(mid) {
  var checkbox = $('#compose-attach-key-' + mid);
  var hiddenak = $('#compose-hidden-attach-key-' + mid);
  if (checkbox.is(':checked')) {
    hiddenak.val('yes');
  } else {
    hiddenak.val('no');
  }
};
