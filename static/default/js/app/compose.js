/* Generate New Draft MID */
MailPile.prototype.compose = function(data) {

  $.ajax({
    url      : mailpile.api.compose,
    type     : 'POST',
    data     : data,
    dataType : 'json'
  }).done(function(response) {

    if (response.status === 'success') {
      window.location.href = mailpile.urls.message_draft + response.result.created + '/';
    } else {
      mailpile.notification(response.status, response.message);
    }
  });
}

/* Composer - Crypto */
MailPile.prototype.compose_load_crypto_states = function() {

  var state = $('#compose-crypto').val();
  var signature = 'none';
  var encryption = 'none';

  if (state.match(/sign/)) {
    signature = 'sign';
  }
  if (state.match(/encrypt/)) {
    encryption = 'encrypt';
  }

  console.log(signature + ' ' + encryption);

  mailpile.compose_render_signature(signature);
  mailpile.compose_render_encryption(encryption);
};

MailPile.prototype.compose_set_crypto_state = function() {
  
  // Returns: none, openpgp-sign, openpgp-encrypt and openpgp-sign-encrypt
  var state = 'none';
  var signature = $('#compose-signature').val();
  var encryption = $('#compose-encryption').val();

  if (signature == 'sign' && encryption == 'encrypt') {
    state = 'openpgp-sign-encrypt'; 
  }
  else if (signature == 'sign') {
    state = 'opengpg-sign';
  }
  else if (encryption == 'encrypt') {
    state = 'openpgp-encrypt';
  }
  else {
    state = 'none';
  }

  $('#compose-crypto').val(state);

  return state;
}

MailPile.prototype.compose_determine_signature = function() {

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

MailPile.prototype.compose_render_signature = function(status) {

  if (status === 'sign') {
    $('.compose-crypto-signature').attr('title', 'This message is signed by your key');
    $('.compose-crypto-signature span.icon').removeClass('icon-signature-none').addClass('icon-signature-verified');
    $('.compose-crypto-signature span.text').html($('.compose-crypto-signature').data('crypto_signed'));
    $('.compose-crypto-signature').removeClass('none').addClass('signed bounce');

  } else if (status === 'none') {
    $('.compose-crypto-signature').attr('title', 'This message is not signed by your key');
    $('.compose-crypto-signature span.icon').removeClass('icon-signature-verified').addClass('icon-signature-none');
    $('.compose-crypto-signature span.text').html($('.compose-crypto-signature').data('crypto_not_signed'));
    $('.compose-crypto-signature').removeClass('signed').addClass('none bounce');

  } else {
    $('.compose-crypto-signature').attr('title', 'Error accesing your key');
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

    this.compose_set_crypto_state();
  }
};

MailPile.prototype.compose_determine_encryption = function(contact) {

  var status = 'none';
  var addresses  = $('#compose-to').val() + ', ' + $('#compose-cc').val() + ', ' + $('#compose-bcc').val();
  var recipients = addresses.split(/, */);

  if (contact) {
    recipients.push(contact);
  }

  var count_total = 0;
  var count_secure = 0;
    
  $.each(recipients, function(key, value){  
    if (value) {
      count_total++;
      var check = mailpile.compose_analyze_address(value);
      if (check.flags.secure) {
        count_secure++;
      }
    }
  });

  if (count_secure === count_total && count_secure !== 0) {
    status = 'encrypt';
  }
  else if (count_secure < count_total && count_secure > 0) {
    status = 'partial';
  }

  return status;
};

MailPile.prototype.compose_render_encryption = function(status) {

  if (status == 'encrypt') {
    $('.compose-crypto-encryption').attr('title', 'This message is encrypted. The recipients & subject are not');
    $('.compose-crypto-encryption span.icon').removeClass('icon-lock-open').addClass('icon-lock-closed');
    $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_encrypt'));
    $('.compose-crypto-encryption').removeClass('none error partial').addClass('encrypted');

  } else if (status === 'partial') {
    $('.compose-crypto-encryption').attr('title', 'This message is encrypted. The recipients & subject are not');
    $('.compose-crypto-encryption span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
    $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_partial_encrypt'));
    $('.compose-crypto-encryption').removeClass('none encrypted error').addClass('partial');

  } else if (status === 'none') {
    $('.compose-crypto-encryption').attr('title', 'This message is encrypted. The recipients & subject are not');
    $('.compose-crypto-encryption span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
    $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_none'));
    $('.compose-crypto-encryption').removeClass('encrypted partial error').addClass('none');

  } else {
    $('.compose-crypto-encryption').attr('title', 'Error prepping this message for encryption');
    $('.compose-crypto-encryption span.icon').removeClass('icon-lock-open icon-lock-closed').addClass('icon-lock-error');
    $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_cannot_encrypt'));
    $('.compose-crypto-encryption').removeClass('encrypted partial none').addClass('error');
  }

  // Set Form Value
  if ($('#compose-encryption').val() !== status) {

    $('.compose-crypto-encryption').addClass('bounce');
    $('#compose-encryption').val(status);

    // Remove Animation
    setTimeout(function() {
      $('.compose-crypto-encryption').removeClass('bounce');
    }, 1000);
    
    this.compose_set_crypto_state();
  }
};


/* Composer - To, Cc, Bcc */
MailPile.prototype.compose_analyze_address = function(address) {
  var check = address.match(/([^<]+?)\s<(.+?)(#[a-zA-Z0-9]+)?>/);
  if (check) {
    if (check[3]) {
      return {"id": check[2], "fn": $.trim(check[1]), "address": check[2], "keys": [{ "fingerprint": check[3].substring(1) }], "flags": { "secure" : true } };
    }
    return {"id": check[2], "fn": $.trim(check[1]), "address": check[2], "flags": { "secure" : false } };
  } else {
    return {"id": address, "fn": address, "address": address, "flags": { "secure" : false }};
  }
}

MailPile.prototype.compose_analyze_recipients = function(addresses) {

  var existing = [];

  // Is Valid & Has Multiple
  if (addresses) {

    var multiple = addresses.split(/, */);

    if (multiple.length > 1) {
      $.each(multiple, function(key, value){
        existing.push(mailpile.compose_analyze_address(value));
      });
    } else {
      existing.push(mailpile.compose_analyze_address(multiple[0]));
    }

    return existing;
  }
}


$('#compose-to, #compose-cc, #compose-bcc').select2({
  id: function(object) {
    if (object.flags.secure) {
      address = object.address + '#' + object.keys[0].fingerprint;
    }
    else {
      address = object.address;
    }
    if (object.fn !== "" && object.address !== object.fn) {
      return object.fn + ' <' + address + '>';
    } else {
      return address;
    }
  },
  ajax: { // instead of writing the function to execute the request we use Select2's convenient helper
    url: mailpile.api.contacts,
    quietMillis: 1,
    cache: true,
    dataType: 'json',
    data: function(term, page) {
      return {
        q: term
      };
    },
    results: function(response, page) { // parse the results into the format expected by Select2
      return {
        results: response.result.addresses
      };
    }
  },
  multiple: true,
  allowClear: true,
  width: '100%',
  minimumInputLength: 1,
  minimumResultsForSearch: -1,
  placeholder: 'Type to add contacts',
  maximumSelectionSize: 100,
  tokenSeparators: [", ", ";"],
  createSearchChoice: function(term) {
    // Check if we have an RFC5322 compliant e-mail address
    if (term.match(/(?:[a-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+\/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])/)) {
      return {"id": term, "fn": term, "address": term, "flags": { "secure" : false }};
    // FIXME: handle invalid email addresses with UI feedback
    } else {
      return {"id": term, "fn": term, "address": term, "flags": { "secure" : false }};
    }
  },
  formatResult: function(state) {
    var avatar = '<span class="icon-user"></span>';
    var secure = '<span class="icon-blank"></span>';
    if (state.photo) {
      avatar = '<img src="' + state.photo + '">';
    }
    if (state.flags.secure) {
      secure = '<span class="icon-lock-closed"></span>';
    }
    return '<span class="compose-select-avatar">' + avatar + '</span>\
            <span class="compose-select-name">' + state.fn + secure + '<br>\
            <span class="compose-select-address">' + state.address + '</span>\
            </span>';
  },
  formatSelection: function(state) {
    var avatar = '<span class="icon-user"></span>';
    var name   = state.fn;
    var secure = '<span class="icon-blank"></span>';

    if (state.photo) {
      avatar = '<span class="avatar"><img src="' + state.photo + '"></span>';
    }
    if (!state.fn) {
      name = state.address; 
    }
    if (state.flags.secure) {
      secure = '<span class="icon-lock-closed"></span>';
    }
    return avatar + '<span class="compose-choice-name" title="' + state.address + '">' + name + secure + '</span>';
  },
  formatSelectionTooBig: function() {
    return 'You\'ve added the maximum contacts allowed, to increase this go to <a href="#">settings</a>';
  },
  selectOnBlur: true
});


// Load Existing
$('#compose-to').select2('data', mailpile.compose_analyze_recipients($('#compose-to').val()));
$('#compose-cc').select2('data', mailpile.compose_analyze_recipients($('#compose-cc').val()));
$('#compose-bcc').select2('data', mailpile.compose_analyze_recipients($('#compose-bcc').val()));


// Selection
$('#compose-to, #compose-cc, #compose-bcc').on('select2-selecting', function(e) {
    var status = mailpile.compose_determine_encryption(e.val);
    mailpile.compose_render_encryption(status);
  }).on('select2-removed', function(e) {
    var status = mailpile.compose_determine_encryption();
    mailpile.compose_render_encryption(status);
});


/* Composer - Add Attachment */
MailPile.prototype.attach = function() {}


/* Compose - Create New Blank Message */
$(document).on('click', '#button-compose', function(e) {
	e.preventDefault();
	mailpile.compose();
});


/* Compose - Change Signature Status */
$(document).on('click', '.compose-crypto-signature', function() {
  var status = mailpile.compose_determine_signature();
  var change = '';

  if (status == 'sign') {
    change = 'none';
  } else {
    change = 'sign';
  }

  mailpile.compose_render_signature(change);
});


/* Compose - Show Cc, Bcc */
$(document).on('click', '.compose-show-field', function(e) {
  $(this).hide();
  $('#compose-' + $(this).html().toLowerCase() + '-html').show();
  if ($(this).html().toLowerCase() == 'cc') {
    $('#compose-bcc-show').detach().appendTo("#compose-cc-html label");
  }
});


/* Compose - Subject Field */
$('#compose-from').keyup(function (e) {
  var code = (e.keyCode ? e.keyCode : e.which);
  if (code === 9 && $('#compose-subject:focus').val() === '') {
  }
});


/* Compose - Send, Save, Reply */
$(document).on('click', '.compose-action', function(e) {

  e.preventDefault();
  var action = $(this).val();

  if (action === 'send') {
	  var action_url     = mailpile.api.compose_send;
	  var action_status  = 'success';
	  var action_message = 'Your message was sent <a id="status-undo-link" data-action="undo-send" href="#">undo</a>';
  }
  else if (action == 'save') {
	  var action_url     = mailpile.api.compose_save;
	  var action_status  =  'info';
	  var action_message = 'Your message was saved';
  }
  else if (action == 'reply') {
	  var action_url     = mailpile.api.compose_send;
	  var action_status  =  'success';
	  var action_message = 'Your reply was sent';
  }

	$.ajax({
		url			 : action_url,
		type		 : 'POST',
		data     : $('#form-compose').serialize(),
		dataType : 'json',
	  success  : function(response) {
	    // Is A New Message (or Forward)
      if (action === 'send' && response.status === 'success') {    
        window.location.href = mailpile.urls.message_sent + response.result.thread_ids[0] + "/";
      }
      // Is Thread Reply
      else if (action === 'reply') {
        mailpile.render_thread_message(response.result);
      }
      else {
        mailpile.notification(response.status, response.message);
      }
    },
    error: function() {
      mailpile.notification('error', 'Could not ' + action + ' your message');      
    }
	});
});


/* Compose - Pick Send Date */
$(document).on('click', '.pick-send-datetime', function(e) {

  if ($(this).data('datetime') == 'immediately') {
    $('#reply-datetime-display').html($(this).html());
  }
  else {
    $('#reply-datetime-display').html('in ' + $(this).html());
  }

  $('#reply-datetime span.icon').removeClass('icon-arrow-down').addClass('icon-arrow-right');
});


/* Compose - Details */
$(document).on('click', '#compose-show-details', function(e) {
  e.preventDefault();
  $('#compose-details').slideDown('fast');
});


$(document).ready(function() {

  // Is Drafts
  if (location.href.split("draft/=")[1]) {

    // Reset tabindex for To: field
    $('#search-query').attr('tabindex', '-1');    
  };

  // Load Crypto States
  mailpile.compose_load_crypto_states();

  // Show Crypto Tooltips
  $('.compose-crypto-signatureeee').qtip({
    style: {
     tip: {
        corner: 'right center',
        mimic: 'right center',
        border: 0,
        width: 10,
        height: 10
      },
      classes: 'qtip-tipped'
    },
    position: {
      my: 'right center',
      at: 'left center',
			viewport: $(window),
			adjust: {
				x: -5,  y: 0
			}
    },
    show: {
      delay: 50
    },
    events: {
      show: function(event, api) {

        $('.compose-to').css('background-color', '#fbb03b');
        $('.compose-cc').css('background-color', '#fbb03b');           
        $('.compose-bcc').css('background-color', '#fbb03b');
        $('.compose-from').css('background-color', '#fbb03b');
        $('.compose-subject').css('background-color', '#fbb03b');

        $('.compose-message').css('background-color', '#a2d699');
        $('.compose-attachments').css('background-color', '#a2d699');
      },
      hide: function(event, api) {

        $('.compose-to').css('background-color', '#ffffff');
        $('.compose-cc').css('background-color', '#ffffff');           
        $('.compose-bcc').css('background-color', '#ffffff');
        $('.compose-from').css('background-color', '#ffffff');
        $('.compose-subject').css('background-color', '#ffffff');

        $('.compose-message').css('background-color', '#ffffff');
        $('.compose-attachments').css('background-color', '#ffffff');
      }
    }
  });

});
