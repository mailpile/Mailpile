/* Generate New Draft MID */
MailPile.prototype.compose = function(data) {

  $.ajax({
    url      : mailpile.api.compose,
    type     : 'POST',
    data     : data,
    dataType : 'json'
  })
  .done(function(response) {

    if (response.status == 'success') {
      window.location.href = mailpile.urls.message_draft + response.result.created + '/';
    } else {
      statusMessage(response.status, response.message);
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


/* Is Compose Page -  Probably want to abstract this differently */
if ($('#form-compose').length) {

  // Reset tabindex for To: field
  $('#qbox').attr('tabindex', '');


  var composeContactSelected = function(contact) {
    if (contact.object.secure) {
      console.log('Whee keys ' + contact.object.keys[0].fingerprint);
      $('.message-privacy-state').attr('title', 'The message is encrypted. The recipients & subject are not');
      $('.message-privacy-state').removeClass('icon-unencrypted').addClass('icon-encrypted');
      $('.message-privacy-state').parent().addClass('bounce');
    } else {
    }
  }

  var formatComposeId = function(object) {
    if (object.fn != "" && object.address != object.fn) {
      return object.fn + ' <' + object.address + '>';
    } else {
      return object.address;
    }
  }

  var formatComposeResult = function(state) {
    var avatar = '<span class="icon-user"></span>';
    var secure = '';
    if (state.photo) {
      avatar = '<img src="' + state.photo + '">';
    }    
    if (state.secure) {
      secure = '<span class="icon-verified"></span>';
    }
    return '<span class="compose-select-avatar">' + avatar + '</span><span class="compose-select-name">' + state.fn + secure + '<br><span class="compose-select-address">' + state.address + '</span></span>';
  }

  var formatComposeSelection = function(state) {
    var avatar = '<span class="icon-user"></span>';
    var secure = '';
    if (state.photo) {
      avatar = '<span class="avatar"><img src="' + state.photo + '"></span>';
    }
    if (state.secure) {
      secure = '<span class="icon-verified"></span>';
    }
    return avatar + '<span class="compose-choice-name" title="' + state.address + '">' + state.fn + secure + '</span>';
  }

  var closeMenu = function() {
    console.log($('#compose-to').val());
    $('#compose-to').select2("close");
  }

  $('#compose-to, #compose-cc, #compose-bcc').select2({
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
      results: function(response, page) {
        // parse the results into the format expected by Select2.
        // since we are using custom formatting functions we do not need to alter remote JSON data
        return {
          results: response.result.addresses
        };
      }
    },
    multiple: true,
    allowClear: true,
    width: '450px',
    minimumInputLength: 1,
    minimumResultsForSearch: -1,
    maximumSelectionSize: 200,
    tokenSeparators: [",", ";"],
    createSearchChoice: function(term) {
      // Check if we have an RFC5322 compliant e-mail address:
      if (term.match(/(?:[a-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+\/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])/)) {
        return {"id": term, "fn": term, "address": term};
      }
      return null;
    },
    formatResult: formatComposeResult,
    formatSelection: formatComposeSelection,
    formatSelectionTooBig: function() {
      return 'You\'ve added the maximum contacts allowed, to increase this go to <a href="#">settings</a>';
    },
    selectOnBlur: true
  });

  $('#compose-to').on('change', function(e) {
    }).on('select2-selecting', function(e) {
      composeContactSelected(e);
      console.log('Selecting ' + e.val);
    }).on('select2-removing', function(e) {
      console.log('Removing ' + e.val);
    }).on('select2-removed', function(e) {
      console.log('Removed ' + e.val);
    }).on('select2-blur', function(e){
      console.log('Blur ' + e.val);
  });

}

/* Show Cc, Bcc */
$(document).on('click', '.compose-show-field', function(e) {
  $(this).hide();
  $('#compose-' + $(this).html().toLowerCase() + '-html').show();
});


/* Subject Field */
$('#compose-from').keyup(function (e) {
  var code = (e.keyCode ? e.keyCode : e.which);
  if (code == 9 && $('#compose-subject:focus').val() == '') {
  }
});

$('#compose-subject').on('focus', function() {
  //this.focus();
  //this.select();
});


/* Send & Save */
$(document).on('click', '.compose-action', function(e) {

  e.preventDefault();
  var action = $(this).val();

  if (action == 'send') {
	  var action_url     = mailpile.api.compose_send;
	  var action_status  = 'success';
	  var action_message = 'Your message was sent <a id="status-undo-link" data-action="undo-send" href="#">undo</a>';
  }
  else if (action == 'save') {
	  var action_url     = mailpile.api.compose_save;
	  var action_status  =  'info';
	  var action_message = 'Your message was saved';
  }

	$.ajax({
		url			 : action_url,
		type		 : 'POST',
		data     : $('#form-compose').serialize(),
		dataType : 'json',
	  success  : function(response) {

      if (action == 'send' && response.status == 'success') {
        window.location.href = mailpile.urls.message_sent + response.result.messages[0].mid;
      }
      else {
        statusMessage(response.status, response.message);
      }
	  }
	});
});
