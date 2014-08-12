/* Composer - To, Cc, Bcc */
Mailpile.compose_analyze_address = function(address) {
  var check = address.match(/([^<]+?)\s<(.+?)(#[a-zA-Z0-9]+)?>/);
  if (check) {
    if (check[3]) {
      return {"id": check[2], "fn": $.trim(check[1]), "address": check[2], "keys": [{ "fingerprint": check[3].substring(1) }], "flags": { "secure" : true } };
    }
    return {"id": check[2], "fn": $.trim(check[1]), "address": check[2], "flags": { "secure" : false } };
  } else {
    return {"id": address, "fn": address, "address": address, "flags": { "secure" : false }};
  }
};


/* Compose - */
Mailpile.compose_analyze_recipients = function(addresses) {

  var existing = [];

  // Is Valid & Has Multiple
  if (addresses) {
    // FIXME: Only solves the comma specific issue. We should do a full RFC 2822 solution eventually.
    var multiple = addresses.split(/>, */);

    if (multiple.length > 1) {
      $.each(multiple, function(key, value){
        existing.push(Mailpile.compose_analyze_address(value + '>')); // Add back on the '>' since the split pulled it off.
      });
    } else {
      existing.push(Mailpile.compose_analyze_address(multiple[0] + '>'));
    }

    return existing;
  }
};


/* Compose - Instance of select2 contact selecting */
Mailpile.compose_address_field = function(id) {

  // Get MID
  var mid = $('#'+id).data('mid');

  //
  $('#' + id).select2({
    id: function(object) {
      if (object.flags.secure) {
        address = object.address + '#' + object.keys[0].fingerprint;
      } else {
        address = object.address;
      }
      if (object.fn !== "" && object.address !== object.fn) {
        return object.fn + ' <' + address + '>';
      } else {
        return address;
      }
    },
    ajax: { // instead of writing the function to execute the request we use Select2's convenient helper
      url: Mailpile.api.contacts,
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
    formatSelection: function(state, elem) {

      // Add To Model
      Mailpile.instance.search_addresses.push(state);

      // Create HTML
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
      return '<div class="compose-choice-wrapper" data-address="' + state.address + '">' + avatar + '<span class="compose-choice-name" data-address="' + state.address + '">' + name + secure + '</span></div>';
    },
    formatSelectionTooBig: function() {
      return 'You\'ve added the maximum contacts allowed, to increase this go to <a href="#">settings</a>';
    },
    selectOnBlur: true
  });

  /* Check encryption state */
  $('#' + id).select2('data', Mailpile.compose_analyze_recipients($('#' + id).val()));

  /* On select update encryption state */
  $('#' + id).on('select2-selecting', function(e) {
      var status = Mailpile.compose_determine_encryption(mid, e.val);
      Mailpile.compose_render_encryption(status);
    }).on('select2-removed', function(e) {
      var status = Mailpile.compose_determine_encryption(mid, false);
      Mailpile.compose_render_encryption(status);
  });
};


$(document).on('click', '.compose-contact-find-keys', function() {
  var address = $(this).data('address');
  Mailpile.find_encryption_keys(address);
});


/* Compose - Change Encryption Status */
$(document).on('click', '.compose-crypto-encryption', function() {
  var status = $('#compose-encryption').val();
  var change = '';
  var mid = $(this).data('mid');

  if (status == 'encrypt') {
    change = 'none';
  } else {
    if (Mailpile.compose_determine_encryption(mid, false) == "encrypt") {
      change = 'encrypt';
    }
  }

  Mailpile.compose_render_encryption(change);
  Mailpile.tooltip_compose_crypto_encryption();
});


/* Compose - Change Signature Status */
$(document).on('click', '.compose-crypto-signature', function() {
  var status = Mailpile.compose_determine_signature();
  var change = '';

  if (status == 'sign') {
    change = 'none';
  } else {
    change = 'sign';
  }

  Mailpile.compose_render_signature(change);
  Mailpile.tooltip_compose_crypto_signature();
});


/* Compose - Show Cc, Bcc */
$(document).on('click', '.compose-show-field', function(e) {
  $(this).hide();
  var field = $(this).text().toLowerCase();
  $('#compose-' + field + '-html').show().removeClass('hide');
});


$(document).on('click', '.compose-hide-field', function(e) {
  var field = $(this).attr('href').substr(1);
  $('#compose-' + field + '-html').hide().addClass('hide');
  $('#compose-' + field + '-show').fadeIn('fast');
});


/* Compose - Quote */
$(document).on('click', '.compose-apply-quote', function(e) {
  e.preventDefault();
  var mid = $(this).data('mid');
  if ($(this).attr('checked')) {
    console.log('is CHECKED ' + mid);
    $(this).attr('checked', false)
  }
  else {
    console.log('is UNCHECKED ' + mid);
    $(this).attr('checked', true)
  }
});


/* Compose - Send, Save, Reply */
$(document).on('click', '.compose-action', function(e) {

  e.preventDefault();
  var action = $(this).val();
  var mid = $(this).parent().data('mid');
  var form_data = $('#form-compose-' + mid).serialize();

  if (action === 'send') {
	  var action_url     = Mailpile.api.compose_send;
	  var action_status  = 'success';
	  var action_message = 'Your message was sent <a id="status-undo-link" data-action="undo-send" href="#">undo</a>';
  }
  else if (action == 'save') {
	  var action_url     = Mailpile.api.compose_save;
	  var action_status  =  'info';
	  var action_message = 'Your message was saved';
  }
  else if (action == 'reply') {
	  var action_url     = Mailpile.api.compose_send;
	  var action_status  =  'success';
	  var action_message = 'Your reply was sent';
  }

	$.ajax({
		url			 : action_url,
		type		 : 'POST',
		data     : form_data,
		dataType : 'json',
	  success  : function(response) {
	    // Is A New Message (or Forward)
      if (action === 'send' && response.status === 'success') {
        window.location.href = Mailpile.urls.message_sent + response.result.thread_ids[0] + "/";
      }
      // Is Thread Reply
      else if (action === 'reply' && response.status === 'success') {
        Mailpile.compose_render_message_thread(response.result.thread_ids[0]);
      }
      else {
        Mailpile.notification(response.status, response.message);
      }
    },
    error: function() {
      Mailpile.notification('error', 'Could not ' + action + ' your message');
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
$(document).on('click', '.compose-show-details', function(e) {
  e.preventDefault();
  var mid = $(this).data('mid');
  var new_message = $(this).data('message');
  if ($('#compose-details-' + mid).hasClass('hide')) {
    var old_message = $(this).html();
    $('#compose-details-' + mid).slideDown('fast').removeClass('hide');
    $('#compose-to-summary-' + mid).hide();
    $(this).html('<span class="icon-eye"></span> <span class="text">' + new_message + '</span>');
    $(this).data('message', old_message).attr('data-message', old_message);
  } else {
    var old_message = $(this).find('.text').html();
    $('#compose-details-' + mid).slideUp('fast').addClass('hide');
    $('#compose-to-summary-' + mid).show();
    $(this).html(new_message);
    $(this).data('message', old_message).attr('data-message', old_message);
  }
});


/* Compose - Create a new email to an address */
$(document).on('click', '.compose-to-email', function(e) {
  e.preventDefault();
  var address = $(this).attr('href').replace('mailto:', '');
  Mailpile.API.message_compose({to: address}, function(response) {
    if (response.status === 'success') {
      window.location.href = Mailpile.urls.message_draft + response.result.created[0] + '/';
    } else {
      Mailpile.notification(response.status, response.message);
    }
  });
});


/* Compose - Delete message that's in a composer */
$(document).on('click', '.compose-message-trash', function() {
  var mid = $(this).data('mid');
  //Mailpile.API.message_unthread({ mid: mid }, function(response) {
  $.ajax({
    url      : '/api/0/message/unthread/',
    type     : 'POST',
    data     : { mid: mid },
    success  : function(response) {
      Mailpile.API.tag_post({mid: mid, add: 'trash', del: ['drafts', 'blank']}, function(response_2) {
        if (response_2.status == 'success') {
          $('#form-compose-' + mid).slideUp('fast');
        } else {
          Mailpile.notification(response_2.status, response_2.message);
        }
      });
    }
  });
});


$(document).on('click', '.compose-from', function(e) {
  e.preventDefault();
  var mid = $(this).data('mid');
  var avatar = $(this).find('.avatar img').attr('src');
  var name = $(this).find('.name').html();
  var address = $(this).find('.address').html();
  $('#compose-from-selected-' + mid).find('.avatar img').attr('src', avatar);
  $('#compose-from-selected-' + mid).find('.name').html(name);
  $('#compose-from-selected-' + mid).find('.address').html(address);
  $('#compose-from-' + mid).val(name + ' <' + address + '>');
});


/* Compose - Autogrow composer boxes */
$(document).on('focus', '.compose-text', function() {
  $(this).autosize();
});


/* Compose - DOM ready */
$(document).ready(function() {

  // Is Drafts
  if (location.href.split("draft/=")[1]) {

    // Reset tabindex for To: field
    $('#search-query').attr('tabindex', '-1');
  };

  // Is Drafts or Thread
  if (location.href.split("draft/=")[1] || location.href.split("thread/=")[1]) {

    // Load Crypto States
    // FIXME: needs dynamic support for multi composers on a page
    Mailpile.compose_load_crypto_states();

    // Instantiate select2
    $('.compose-address-field').each(function(key, elem) {
      Mailpile.compose_address_field($(elem).attr('id'));
    });

    // Save Text Composing Objects
    $('.compose-text').each(function(key, elem) {
        Mailpile.messages_composing[$(elem).attr('id')] = $(elem).val()
    });

    // Run Autosave
    Mailpile.compose_autosave_timer.play();
    Mailpile.compose_autosave_timer.set({ time : 20000, autostart : true });

    // Initialize Attachments
    // FIXME: needs dynamic support for multi composers on a page
    $('.compose-attachments').each(function(key, elem) {
      var mid = $(elem).data('mid');
      console.log('js uploader: ' + mid);
      uploader({
        browse_button: 'compose-attachment-pick-' + mid,
        container: 'compose-attachments-' + mid,
        mid: mid
      });
    });
  }

});
