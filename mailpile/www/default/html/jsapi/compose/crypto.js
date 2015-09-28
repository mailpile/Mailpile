/* Composer - Crypto */

Mailpile.Composer.Crypto.UpdateEncryptionState = function(mid, chain) {
  // Assemble all the recipient addresses, as well as our sending address
  var emails = [$('#compose-from-selected-' + mid).find('.address').html()];
  Mailpile.Composer.Recipients.GetAll(mid, function(rcpt) {
    emails.push(rcpt.address);
  });
  // Ask the back-end for updated address-book info and an aggregate
  // recommended crypto policy.
  Mailpile.API.crypto_policy_get({email: emails}, function(response) {
    var r = response.result;

    // Update attach key (or not) state
    if (r['can-sign']) {
      $('.compose-attach-key').show();
    }
    else {
      $('.compose-attach-key').hide();
    }
    $('#compose-attach-key-' + mid).prop('checked',
                                         r['can-sign'] && r['send-keys']);
    Mailpile.Composer.Crypto.AttachKey(mid);

    // Record our capabilities: can we encrypt? Sign?
    $('#compose-crypto-encryption-' + mid).data('can', r['can-encrypt']);
    $('#compose-crypto-signature-' + mid).data('can', r['can-sign']);
    if (emails.length > 1) {
      // Update encrypt/sign icons
      Mailpile.Composer.Crypto.LoadStates(mid, r['crypto-policy'],
                                               r['reason']);

      // Embellish our recipients with data from the backend; in particular
      // this adds the keys and avatars to things manually typed.
      Mailpile.Composer.Recipients.WithToCcBcc(mid, function(field, rcpts) {
        var changed = false;
        for (var i in rcpts) {
          var updated = r.addresses[rcpts[i].address];
          if (updated) {
            if (rcpts[i].fn.indexOf(' ') < 0) rcpts[i].fn = updated.fn;
            rcpts[i].keys = updated.keys;
            rcpts[i].flags = updated.flags;
            rcpts[i].photo = updated.photo;
            changed = true;
          }
        };
        if (changed) Mailpile.Composer.Recipients.Update(mid, field, rcpts);
      });
    }
    else {
      Mailpile.Composer.Crypto.LoadStates(mid, 'none', '');
    }
    if (chain) chain(mid);
  });
};


Mailpile.Composer.Crypto.Unencryptables = function(mid) {
  var unencryptable = [];
  Mailpile.Composer.Recipients.GetAll(mid, function(rcpt) {
    if (!rcpt.flags.secure) unencryptable.push(rcpt);
  });
  return unencryptable;
};


Mailpile.Composer.Crypto.LoadStates = function(mid, state, reason) {
  state = state || $('#compose-crypto-' + mid).val();

  var signature = 'none';
  if (state.match(/sign/)) {
    signature = 'sign';
  }
  Mailpile.Composer.Crypto.SignatureToggle(signature, mid);

  var encryption = 'none';
  if (state.match(/encrypt/)) {
    encryption = 'encrypt';
  }
  Mailpile.Composer.Crypto.EncryptionToggle(encryption, mid);

  // FIXME: We need to know if encryption or signing is REQUIRED, and
  // disable or enable the send button based on that. The conflict state
  // doesn't cover for when the user does illegal things manually.
  $('#form-compose-' + mid + ' button[name=send]')
    .data('crypto-state', state || '')
    .data('crypto-reason', reason || '')
    .attr('title', reason || '')
    .css({ 'opacity': (state.match(/conflict/)) ? 0.25 : 1.0 });
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


/* Compose - Render crypto "signature" of a message */
Mailpile.Composer.Crypto.SignatureToggle = function(status, mid, manual) {
  if ($('#compose-crypto-signature-' + mid).data('can') === false) {
    status = (status == 'cannot') ? status : 'none';
  }
  if (status === 'sign') {
    $('#compose-crypto-signature-' + mid).data('crypto_color', 'crypto-color-green');
    $('#compose-crypto-signature-' + mid).attr('title', '{{_("This message will be verifiable to recipients who have your encryption key. They will know it actually came from you :)")|escapejs}}');
    $('#compose-crypto-signature-' + mid).find('span.icon').removeClass('icon-signature-none').addClass('icon-signature-verified');
    $('#compose-crypto-signature-' + mid).find('span.text').html('{{_("Signed")|escapejs}}');
    $('#compose-crypto-signature-' + mid).removeClass('none').addClass('signed bounce');

  } else if (status === 'none') {
    $('#compose-crypto-signature-' + mid).data('crypto_color', 'crypto-color-gray');
    $('#compose-crypto-signature-' + mid).attr('title', '{{_("This message will not be verifiable, recipients will have no way of knowing it actually came from you.")|escapejs}}');
    $('#compose-crypto-signature-' + mid).find('span.icon').removeClass('icon-signature-verified').addClass('icon-signature-none');
    $('#compose-crypto-signature-' + mid).find('span.text').html('{{_("Unsigned")|escapejs}}');
    $('#compose-crypto-signature-' + mid).removeClass('signed').addClass('none bounce');

  } else {
    $('#compose-crypto-signature-' + mid).data('crypto_color', 'crypto-color-red');
    $('#compose-crypto-signature-' + mid).attr('title', '{{_("Verification Error")|escapejs}}');
    $('#compose-crypto-signature-' + mid).find('span.icon').removeClass('icon-signature-none icon-signature-verified').addClass('icon-signature-error');
    $('#compose-crypto-signature-' + mid).find('span.text').html('{{_("Error accessing your encryption key")|escapejs}}');
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
Mailpile.Composer.Crypto.EncryptionToggle = function(status, mid, manual) {
  var encryption = $('#compose-encryption-' + mid).val();
  var can = $('#compose-crypto-encryption-' + mid).data('can');
  if (!manual && (status === 'none') && (encryption === 'encrypt') && !can) {
    // If we were encrypting, but as a side-effect are no longer capable of
    // doing so, then we go to the "cannot" state instead of "none".
    status = 'cannot';
  }
  else if (!can) {
    status = (status == 'cannot') ? status : 'none';
  }

  if (status === 'encrypt') {
    $('#compose-crypto-encryption-' + mid).data('crypto_color', 'crypto-color-green');
    $('#compose-crypto-encryption-' + mid).attr('title', '{{_("This message and attachments will be encrypted. The recipients & subject (metadata) will not")|escapejs}}');
    $('#compose-crypto-encryption-' + mid).find('span.icon').removeClass('icon-lock-open').addClass('icon-lock-closed');
    $('#compose-crypto-encryption-' + mid).find('span.text').html('{{_("Encrypted")|escapejs}}');
    $('#compose-crypto-encryption-' + mid).removeClass('none error cannot').addClass('encrypted');

  } else if (status === 'cannot') {
    $('#compose-crypto-encryption-' + mid).data('crypto_color', 'crypto-color-orange');
    $('#compose-crypto-encryption-' + mid).attr('title', '{{_("This message cannot be encrypted because you do not have keys for one or more recipients")|escapejs}}');
    $('#compose-crypto-encryption-' + mid).find('span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
    $('#compose-crypto-encryption-' + mid).find('span.text').html('{{_("Can Not Encrypt")|escapejs}}');
    $('#compose-crypto-encryption-' + mid).removeClass('none encrypted error').addClass('cannot');

  } else if (status === 'none' || status == '') {
    $('#compose-crypto-encryption-' + mid).data('crypto_color', 'crypto-color-gray');
    $('#compose-crypto-encryption-' + mid).attr('title', '{{_("This message and metadata will not be encrypted")|escapejs}}');
    $('#compose-crypto-encryption-' + mid).find('span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
    $('#compose-crypto-encryption-' + mid).find('span.text').html('{{_("None")|escapejs}}');
    $('#compose-crypto-encryption-' + mid).removeClass('encrypted cannot error').addClass('none');

  } else {
    $('#compose-crypto-encryption-' + mid).data('crypto_color', 'crypto-color-red');
    $('#compose-crypto-encryption-' + mid).attr('title', '{{_("There was an error prepping this message for encryption")|escapejs}}');
    $('#compose-crypto-encryption-' + mid).find('span.icon').removeClass('icon-lock-open icon-lock-closed').addClass('icon-lock-error');
    $('#compose-crypto-encryption-' + mid).find('span.text').html('{{_("Error Encrypting")|escapejs}}');
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
