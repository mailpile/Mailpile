/* Composer - Analyze cyrpto state of a message */
Mailpile.compose_load_crypto_states = function() {

  var state = $('#compose-crypto').val();
  var signature = 'none';
  var encryption = 'none';

  if (state.match(/sign/)) {
    signature = 'sign';
  }
  if (state.match(/encrypt/)) {
    encryption = 'encrypt';
  }

  Mailpile.compose_render_signature(signature);
  Mailpile.compose_render_encryption(encryption);
};


/* Compose - Set crypto state of message */
Mailpile.compose_set_crypto_state = function() {
  
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
Mailpile.compose_determine_signature = function() {

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
Mailpile.compose_determine_encryption = function(mid, contact) {

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
      var check = Mailpile.compose_analyze_address(value);
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