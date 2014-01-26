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


/* Add Attachment */
MailPile.prototype.attach = function() {}


/* Create New Blank Message */
$(document).on('click', '#button-compose', function(e) {
	e.preventDefault();
	mailpile.compose();
});


/* Compose Page */



var composeContactSelected = function(contact) {
  if (contact.object.flags.secure) {
    $('.message-crypto-encryption').attr('title', 'This message is encrypted. The recipients & subject are not');
    $('.message-crypto-encryption span.icon').removeClass('icon-lock-open').addClass('icon-lock-closed');
    $('.message-crypto-encryption span.text').html($('.message-crypto-encryption').data('crypto_encrypt'));
    $('.message-crypto-encryption').addClass('bounce');

    $('#compose-encryption').val('openpgp-sign-encrypt');
  } else {
    $('.message-crypto-encryption').attr('title', 'This message is encrypted. The recipients & subject are not');
    $('.message-crypto-encryption span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
    $('.message-crypto-encryption span.text').html($('.message-crypto-encryption').data('crypto_cannot_encrypt'));
    $('.message-crypto-encryption').addClass('bounce');

    $('#compose-encryption').val('openpgp-sign');
  }
}


var formatComposeId = function(object) {
  if (object.fn !== "" && object.address !== object.fn) {
    return object.fn + ' <' + object.address + '>';
  } else {
    return object.address;
  }
}

var formatComposeResult = function(state) {
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
}

var formatComposeSelection = function(state) {
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
}

var loadExistingEmails = function(addresses) {

  var existing = [];

  if (addresses) {

    // Check for Name & Value
    function analyzeRecipient(address) {
      var check = address.match(/([^<]+)\s<(.*)>/);
      if (check) {      
        return {"id": check[2], "fn": check[1], "address": check[2], "flags": { "secure" : false }};
      } else {
        return {"id": addresses, "fn": addresses, "address": addresses, "flags": { "secure" : false }};
      }
    }

    // Check for Multiple Addresses
    var multiple = addresses.split(", ");

    if (multiple.length > 1) {
      $.each(multiple, function(key, value){
        analyzeRecipient(value);      
        existing.push(analyzeRecipient(value));
      });
    } else {
      existing.push(analyzeRecipient(multiple[0]));
    }

    return existing;
  }
}

$('#compose-to').select2({
  id: formatComposeId,
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
    results: function(response, page) {  // parse the results into the format expected by Select2
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
  placeholder: 'type to add contacts',
  maximumSelectionSize: 100,
  tokenSeparators: [",", ";"],
  createSearchChoice: function(term) {
    // Check if we have an RFC5322 compliant e-mail address:
    if (term.match(/(?:[a-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+\/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])/)) {
      return {"id": term, "fn": term, "address": term, "flags": { "secure" : false }};
    } else {
      return {"id": term, "fn": term, "address": term, "flags": { "secure" : false }};
    }
  },
  formatResult: formatComposeResult,
  formatSelection: formatComposeSelection,
  formatSelectionTooBig: function() {
    return 'You\'ve added the maximum contacts allowed, to increase this go to <a href="#">settings</a>';
  },
  selectOnBlur: true 
});

// Load Existing
$('#compose-to').select2('data', loadExistingEmails($('#compose-to').val()));


$('#compose-to').on('change', function(e) {
    //console.log('Cha cha changes');
  }).on('select2-selecting', function(e) {
    composeContactSelected(e);
    console.log('Selecting ' + e.val);
  }).on('select2-removing', function(e) {
    //console.log('Removing ' + e.val);
  }).on('select2-removed', function(e) {
    console.log('Removed ' + e.val);
  }).on('select2-blur', function(e){
    //console.log('Blur ' + e.val);
});



/* Show Cc, Bcc */
$(document).on('click', '.compose-show-field', function(e) {
  $(this).hide();
  $('#compose-' + $(this).html().toLowerCase() + '-html').show();
  if ($(this).html().toLowerCase() == 'cc') {
    $('#compose-bcc-show').detach().appendTo("#compose-cc-html label");
  }
});


/* Subject Field */
$('#compose-from').keyup(function (e) {
  var code = (e.keyCode ? e.keyCode : e.which);
  if (code === 9 && $('#compose-subject:focus').val() === '') {
  }
});


/* Send, Save, Reply */
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

  // Reset tabindex for To: field
  if (location.href.split("draft/=")[1]) {
    $('#search-query').attr('tabindex', '-1');
  };
  
  // Show Crypto Tooltips
  $('.message-crypto-encryption').qtip({
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