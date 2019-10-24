/* Composer - Crypto */

Mailpile.Composer.Crypto.UpdateEncryptionState = function(mid, chain, initial) {
  // Assemble all the recipient addresses, as well as our sending address
  var emails = [$('#compose-from-selected-' + mid).find('.address').html()];
  Mailpile.Composer.Recipients.GetAll(mid, function(rcpt) {
    emails.push(rcpt.address);
  });
  // Ask the back-end for updated address-book info and an aggregate
  // recommended crypto policy.
  var cp_args = {email: emails};
  if ($('form#form-compose-' + mid).data('should-encrypt') == 'Y') {
    cp_args['should-encrypt'] = 'Y';
  };
  Mailpile.API.crypto_policy_get(cp_args, function(response) {
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

    var policy = undefined;
    var changes = 0;
    if (emails.length > 1) {

      if (!initial) {
        // Record reason for current policy (I could not find a better place
        // than the send button) but there sure is :)
        Mailpile.Composer.Crypto.SendButton().data('policy-reason', r['reason']);
        policy = r['crypto-policy'];
      }

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
            changes += 1;
          }
        };
        if (changed) Mailpile.Composer.Recipients.Update(mid, field, rcpts);
      });
    }

    if (changes || initial) {
      Mailpile.API.async_crypto_keytofu_post(cp_args, function(data, ev) {
        if (data.result && data.result.imported_keys)
        {
          for (key in data.result.imported_keys) {
            Mailpile.Composer.Crypto.UpdateEncryptionState(mid);
            return;
          }
        }
      });
    }

    // Update encrypt/sign icons
    Mailpile.Composer.Crypto.LoadStates(mid, policy);
    Mailpile.Composer.Crypto.SetState(mid);
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


Mailpile.Composer.Crypto.LoadStates = function(mid, state) {
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

  Mailpile.Composer.Crypto.UpdateSendButton(mid, state);
};

/* Compose - Retrieve a jQuery instance of the Send button */
Mailpile.Composer.Crypto.SendButton = function(mid) {
  return $('#form-compose-' + mid + ' button[name=send]');
};

/* Compose - Update the display properties for the send button */
Mailpile.Composer.Crypto.UpdateSendButton = function(mid, state) {
  // FIXME: We need to know if encryption or signing is REQUIRED, and
  // disable or enable the send button based on that. The conflict state
  // doesn't cover for when the user does illegal things manually.
  var cryptoStateMessage = Mailpile.Composer.Crypto.GetCryptoStateMessage(mid);

  Mailpile.Composer.Crypto.SendButton(mid)
    .data('crypto-state', state)
    .data('crypto-reason', cryptoStateMessage)
    .attr('title', cryptoStateMessage)
    .css({ 'opacity': (state.match(/conflict/)) ? 0.25 : 1.0 });
};


/* Compose - Build crypto state message depending on current crypto selection */
Mailpile.Composer.Crypto.GetCryptoStateMessage = function(mid) {
  var currentState = Mailpile.Composer.Crypto.GetState(mid);
  var policyReason = Mailpile.Composer.Crypto.SendButton(mid).data('policy-reason') || '';
  var message = {
    "none":                 '{{_("Neither signing nor encrypting.")|escapejs}}',
    "openpgp-sign":         '{{_("Signing but not encrypting.")|escapejs}}',
    "openpgp-encrypt":      '{{_("Encrypting but not signing.")|escapejs}}',
    "openpgp-sign-encrypt": '{{_("Signing and encrypting.")|escapejs}}',
  }[currentState] || ('{{_("Undefined state: ")|escapejs}}' + currentState);
  return [message, policyReason].join(" ").trim();
};


/* Compose - Set crypto state of message */
Mailpile.Composer.Crypto.SetState = function(mid) {
  var newState = Mailpile.Composer.Crypto.GetState(mid);
  $('#compose-crypto-' + mid).val(newState);
  return newState;
};


/* Compose - Determine and return current crypto state of message */
Mailpile.Composer.Crypto.GetState = function(mid) {
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
  return state;
};


/* Compose - Render crypto "signature" of a message */
Mailpile.Composer.Crypto.SignatureToggle = function(status, mid, manual) {
  $elem = $('#compose-crypto-signature-' + mid);

  // If manually set, store new preference for signing.
  if (manual === 'manual') {
    $elem.data('should', (status === 'sign'));
  }

  // If no preference for signing is stored, enable it.
  var shouldSign = $elem.data('should');
  shouldSign = (undefined === shouldSign) ? (status === 'sign') : shouldSign;

  // If signin capibilities can not be detected, default to false.
  var canSign = $elem.data('can');
  canSign = (undefined === canSign) ? false : canSign;

  // FIXME: Could/Should we store that on the element instead of passing it
  // via `status` object.
  if (status == 'cannot') {
    canSign = false;
  }

  var willSign = canSign && shouldSign;
  var newState = willSign ? 'sign' : status;

  if (status === 'cannot') {
    $elem.data('crypto_color', 'crypto-color-red');
    $elem.attr('title', '{{_("Verification Error")|escapejs}}');
    $elem.find('span.icon').removeClass('icon-signature-none icon-signature-verified').addClass('icon-signature-error');
    $elem.find('span.text').html('{{_("Error accessing your encryption key")|escapejs}}');
    $elem.removeClass('none').addClass('error bounce');
  }
  else if (willSign) {
    $elem.data('crypto_color', 'crypto-color-green');
    $elem.attr('title', '{{_("This message will be signed and verifiable to recipients who have your encryption key")|escapejs}}');
    $elem.find('span.icon').removeClass('icon-signature-none').addClass('icon-signature-verified');
    $elem.find('span.text').html('{{_("Signed")|escapejs}}');
    $elem.removeClass('none').addClass('signed bounce');

  } else {
    $elem.data('crypto_color', 'crypto-color-gray');
    $elem.attr('title', '{{_("This message will not be verifiable, recipients will have no way of knowing it actually came from you")|escapejs}}');
    $elem.find('span.icon').removeClass('icon-signature-verified').addClass('icon-signature-none');
    $elem.find('span.text').html('{{_("Unsigned")|escapejs}}');
    $elem.removeClass('signed').addClass('none bounce');
  }

  // Set Form Value
  if ($('#compose-signature-' + mid).val() !== newState) {
    $elem.addClass('bounce');
    $('#compose-signature-' + mid).val(newState);

    // Remove Animation
    setTimeout(function() {
      $elem.removeClass('bounce');
    }, 1000);

    Mailpile.Composer.Crypto.UpdateSendButton(mid, newState);
    if (manual) Mailpile.Composer.Crypto.SetState(mid);
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
    $('#compose-crypto-encryption-' + mid).attr('title', '{{_("This message and attachments will be encrypted, unreadable to all but the intended recipients")|escapejs}}');
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
    $('#compose-crypto-encryption-' + mid).attr('title', '{{_("This message and metadata will not be encrypted, if intercepted anyone can read it")|escapejs}}');
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

    if (manual) Mailpile.Composer.Crypto.SetState(mid);
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
