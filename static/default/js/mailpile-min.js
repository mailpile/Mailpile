// Make console.log not crash JS browsers that don't support it
if (!window.console) window.console = { log: $.noop, group: $.noop, groupEnd: $.noop, info: $.noop, error: $.noop };

Number.prototype.pad = function(size) {
	// Unfortunate padding function....
	if(typeof(size) !== "number"){
    size = 2;
  }
	var s = String(this);
	while (s.length < size) s = "0" + s;
	return s;
}

function MailPile() {
  this.instance       = {};
	this.search_cache   = [];
	this.bulk_cache     = [];
	this.keybindings    = [
  	["normal", "/",      function() { 
  	  $("#search-query").focus(); return false;
    }],
  	["normal", "c",      function() { mailpile.compose(); }],
  	["normal", "g i",    function() { mailpile.go("/in/inbox/"); }],
  	["normal", "g c",    function() { mailpile.go("/contact/list/"); }],
  	["normal", "g n c",  function() { mailpile.go("/contact/add/"); }],
  	["normal", "g n m",  function() { mailpile.go("/compose/"); }],
  	["normal", "g t",    function() { 
  	  $("#dialog_tag").show(); $("#dialog_tag_input").focus(); return false; 
    }],
    ["global", "esc",    function() {
  		
  		// Add Form Fields
  		$('#search-query').blur();
  		$('#compose-subject').blur();
      $('#compose-text').blur();
    }]
  ];
	this.commands       = [];
	this.graphselected  = [];
	this.defaults       = {
  	view_size: "comfy"
	}
	this.api = {
    compose      : "/api/0/message/compose/",
    compose_send : "/api/0/message/update/send/",
    compose_save : "/api/0/message/update/",
    contacts     : "/api/0/search/address/",
    message      : "/api/0/message/=",
  	tag          : "/api/0/tag/",
  	tag_add      : "/api/0/tag/add/",
  	search_new   : "/api/0/search/?q=in%3Anew",
  	settings_add : "/api/0/settings/add/"
	}
	this.urls = {
  	message_draft : "/message/draft/=",
  	message_sent  : "/thread/="
	}
	this.plugins = [];
};

MailPile.prototype.go = function(url) {
  window.location.href = url;
};

MailPile.prototype.bulk_cache_add = function(mid) {
  if (_.indexOf(this.bulk_cache, mid) < 0) {
    this.bulk_cache.push(mid);
  }
};

MailPile.prototype.bulk_cache_remove = function(mid) {
  if (_.indexOf(this.bulk_cache, mid) > -1) {
    this.bulk_cache = _.without(this.bulk_cache, mid);
  }
};

MailPile.prototype.show_bulk_actions = function(elements) {
  $.each(elements, function(){    
    $(this).css('visibility', 'visible');
  });
};

MailPile.prototype.hide_bulk_actions = function(elements) {
  $.each(elements, function(){    
    $(this).css('visibility', 'hidden');
  });
};

MailPile.prototype.get_new_messages = function(actions) {    
  $.ajax({
	  url			 : mailpile.api.search_new,
	  type		 : 'GET',
	  dataType : 'json',
    success  : function(response) {
      if (response.status == 'success') {
        actions(response);
      }
    }
  });
};

MailPile.prototype.render = function() {

  // Dynamic CSS Reiszing
  var dynamic_sizing = function() {

    var sidebar_height = $('#sidebar').height();

    // Is Tablet or Mobile
    if ($(window).width() < 1024) {
      var sidebar_width = 0;
    }
    else {
      var sidebar_width = 225;
    }

    var content_width  = $(window).width() - sidebar_width;
    var content_height = $(window).height() - 62;
    var content_tools_height = $('#content-tools').height();
    var fix_content_view_height = sidebar_height - content_tools_height;
  
    $('.sub-navigation').width(content_width);
    $('#thread-title').width(content_width);
  
    // Set Content View
    $('#content-view').css('height', fix_content_view_height).css('top', content_tools_height);

    var new_content_width = $(window).width() - sidebar_width;
    $('.sub-navigation, .bulk-actions').width(new_content_width);
  };

  dynamic_sizing();

  // Resize Elements on Drag
  window.onresize = function(event) {
    dynamic_sizing();
  };

  // Show Mailboxes
  if ($('#sidebar-tag-outbox').find('span.sidebar-notification').html() !== undefined) {
    $('#sidebar-tag-outbox').show();
  }

  // Mousetrap Keybindings
	for (item in mailpile.keybindings) {
	  var keybinding = mailpile.keybindings[item];
		if (keybinding[0] == "global") {
			Mousetrap.bindGlobal(keybinding[1], keybinding[2]);
		} else {
      Mousetrap.bind(keybinding[1], keybinding[2]);
		}
	}

};

var mailpile = new MailPile();
var favicon = new Favico({animation:'popFade'});

// Non-exposed functions: www, setup
$(document).ready(function() {

  // Render
  mailpile.render();

});




/* **********************************************
     Begin notifications.js
********************************************** */

MailPile.prototype.notification = function(status, message_text, complete, complete_action) {

  var default_messages = {
    "success" : "Success, we did exactly what you asked.",
    "info"    : "Here is a basic info update",
    "debug"   : "What kind of bug is this bug, it's a debug",
    "warning" : "This here be a warnin to you, just a warnin mind you",
    "error"   : "Whoa cowboy, you've mozyed on over to an error"
  }

  var message = $('#messages').find('div.' + status);

  if (message_text == undefined) {
    message_text = default_messages[status];
  }

  // Show Message
  message.find('span.message-text').html(message_text),
  message.fadeIn(function() {
  });

	// Complete Action
	if (complete == undefined) {

  }
	else if (complete == 'hide') {
		message.delay(5000).fadeOut('normal', function()
		{
			message.find('span.message-text').empty();
		});
	}
	else if (options.complete == 'redirect') {
		setTimeout(function() { window.location.href = complete_action }, 5000);
	}

  return false;
}


$(document).ready(function() {

  /* Message Close */
	$('.message-close').on('click', function() {
		$(this).parent().fadeOut(function() {
			//$('#header').css('padding-top', statusHeaderPadding());
		});
	});

});

/* **********************************************
     Begin tooltips.js
********************************************** */

// Non-exposed functions: www, setup
$(document).ready(function() {


  $('.topbar-nav a').qtip({
    style: {
     tip: {
        corner: 'top center',
        mimic: 'top center',
        border: 0,
        width: 10,
        height: 10
      },
      classes: 'qtip-tipped'
    },
    position: {
      my: 'top center',
      at: 'bottom center',
			viewport: $(window),
			adjust: {
				x: 0,  y: 5
			}
    },
    show: {
      delay: 350
    }
  });


  $('a.bulk-action').qtip({
    style: {
      classes: 'qtip-tipped'
    },
    position: {
      my: 'top center',
      at: 'bottom center',
			viewport: $(window),
			adjust: {
				x: 0,  y: 5
			}
    }
  });



  $('.compose-to-email').qtip({
    style: {
      classes: 'qtip-tipped'
    },
    position: {
      my: 'bottom center',
      at: 'top center',
			viewport: $(window),
			adjust: {
				x: 0,  y: 0
			}
    },
    show: {
      delay: 500
    }
  });


});

/* **********************************************
     Begin gpg.js
********************************************** */

MailPile.prototype.gpgrecvkey = function(keyid) {
	console.log("Fetching GPG key 0x" + keyid);

}

MailPile.prototype.gpglistkeys = function() {

}

/* **********************************************
     Begin compose.js
********************************************** */

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
    $('.compose-crypto-encryption').attr('title', 'This message is & attachments are encrypted. The recipients & subject are not');
    $('.compose-crypto-encryption span.icon').removeClass('icon-lock-open').addClass('icon-lock-closed');
    $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_encrypt'));
    $('.compose-crypto-encryption').removeClass('none error partial').addClass('encrypted');

  } else if (status === 'partial') {
    $('.compose-crypto-encryption').attr('title', 'This message cannot be encrypted because you do not have keys for one or more recipients');
    $('.compose-crypto-encryption span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
    $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_partial_encrypt'));
    $('.compose-crypto-encryption').removeClass('none encrypted error').addClass('partial');

  } else if (status === 'none') {
    $('.compose-crypto-encryption').attr('title', 'This message is not encrypted');
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


/* Compose - Change Encryption Status */
$(document).on('click', '.compose-crypto-encryption', function() {
  var status = $('#compose-encryption').val();
  var change = '';

  if (status == 'encrypt') {
    change = 'none';
  } else {
    if (mailpile.compose_determine_encryption() == "encrypt") {
      change = 'encrypt';
    }
  }

  mailpile.compose_render_encryption(change);
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
          mailpile.notification(response.status, response.message);
//        mailpile.render_thread_message(response.result);
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


/* Compose - Sent To Email */
$(document).on('click', '.compose-to-email', function(e) {
  e.preventDefault();
/*
  mailpile.compose({
    to: $(this).data('email')
  });
*/
  alert('FIXME: Create New Blank Message To Address');
});


$(document).ready(function() {

  // Is Drafts
  if (location.href.split("draft/=")[1]) {

    // Reset tabindex for To: field
    $('#search-query').attr('tabindex', '-1');
  };

  // Is Drafts or Thread
  if (location.href.split("draft/=")[1] || location.href.split("thread/=")[1]) {

    // Load Crypto States
    mailpile.compose_load_crypto_states();
  }

  // Show Crypto Tooltips
  $('.compose-crypto-signature').qtip({
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
      }
    }
  });

  $('.compose-crypto-encryption').qtip({
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

        $('#s2id_compose-to .select2-choices').css('border-color', '#fbb03b');
        $('#s2id_compose-cc .select2-choices').css('border-color', '#fbb03b');           
        $('#s2id_compose-bcc .select2-choices').css('border-color', '#fbb03b');
        $('.compose-from').css('border-color', '#fbb03b');
        $('.compose-subject input[type=text]').css('border-color', '#fbb03b');

        $('.compose-message textarea').css('border-color', '#a2d699');
        $('.compose-attachments').css('border-color', '1px solid #a2d699');
      },
      hide: function(event, api) {

        $('#s2id_compose-to .select2-choices').css('border-color', '#CCCCCC');
        $('#s2id_compose-cc .select2-choices').css('border-color', '#CCCCCC');           
        $('#s2id_compose-bcc .select2-choices').css('border-color', '#CCCCCC');
        $('.compose-from').css('background-color', '#ffffff');
        $('.compose-subject input[type=text]').css('border-color', '#CCCCCC');

        $('.compose-message textarea').css('border-color', '#CCCCCC');
        $('.compose-attachments').css('border-color', '#F2F2F2');
      }
    }
  });

});

/* **********************************************
     Begin pile.js
********************************************** */

/* Pile - Action Select */
MailPile.prototype.pile_action_select = function(item) {

  // Add To Data Model
  mailpile.bulk_cache_add(item.data('mid'));

	// Increment Selected
	if (mailpile.bulk_cache.length === 1) {
    var message = '<span id="bulk-actions-selected-count">1</span> ' + $('#bulk-actions-message').data('bulk_selected');
    $('#bulk-actions-message').html(message);
    mailpile.show_bulk_actions($('.bulk-actions').find('li.hide'));
	} else {
	  $('#bulk-actions-selected-count').html(mailpile.bulk_cache.length);
  }

	// Style & Select Checkbox
	item.removeClass('result').addClass('result-on')
	.data('state', 'selected')
	.find('td.checkbox input[type=checkbox]')
	.val('selected')
	.prop('checked', true);
};


/* Pile - Action Unselect */
MailPile.prototype.pile_action_unselect = function(item) {

  // Remove From Data Model
  mailpile.bulk_cache_remove(item.data('mid'));

	// Decrement Selected
	$('#bulk-actions-selected-count').html(mailpile.bulk_cache.length);

	// Hide Actions
	if (mailpile.bulk_cache.length < 1) { 
    var message = $('#bulk-actions-message').data('bulk_selected_none');
    $('#bulk-actions-message').html(message);
    mailpile.hide_bulk_actions($('.bulk-actions').find('li.hide'));
	}

	// Style & Unselect Checkbox
	item.removeClass('result-on').addClass('result')
	.data('state', 'normal')
	.find('td.checkbox input[type=checkbox]')
	.val('normal')
	.prop('checked', false);
};

/* Pile - Display */
MailPile.prototype.pile_display = function(current, change) {

  if (change) {
    $('#sidebar').removeClass(current).addClass(change);
    $('#pile-results').removeClass(current).addClass(change);
  } else {
    $('#sidebar').addClass(current);
    $('#pile-results').addClass(current);
  }
  
  setTimeout(function() {

    $('#sidebar').fadeIn('fast');
    $('#pile-results').fadeIn('fast');
  }, 250);
  
}

/* Pile - Bulk Select / Unselect All */
$(document).on('click', '#pile-select-all-action', function(e) {

  var checkboxes = $('#pile-results input[type=checkbox]');

  if ($(this).attr('checked') === undefined) {
    $.each(checkboxes, function() {      
      mailpile.pile_action_select($(this).parent().parent());
    });
    $(this).attr('checked','checked');

  } else {
    $.each(checkboxes, function() {
      mailpile.pile_action_unselect($(this).parent().parent());
    });
    $(this).removeAttr('checked');
  }
});

/* Pile - Bulk Action Link */
$(document).on('click', '.bulk-action', function(e) {

	e.preventDefault();
	var action = $(this).data('action');

  if (action == 'later' || action == 'archive' || action == 'trash') {

    var delete_tag = '';

    if ($.url.segment(0) === 'in') {
     delete_tag = $.url.segment(1);
    }

    // Add / Delete
    mailpile.tag_add_delete(action, delete_tag, mailpile.bulk_cache, function() {

      // Update Pile View
      $.each(mailpile.bulk_cache, function(key, mid) {
        $('#pile-message-' + mid).fadeOut('fast');
      });

      // Empty Bulk Cache
      mailpile.bulk_cache = [];
    });
  }
  else if (action == 'add-to-group') {

    // Open Modal or dropdown with options
  }
  else if (action == 'assign-tags') {

    // Open Modal with selection options
  }
});


/* Pile - Select & Unselect Items */
$(document).on('click', '#pile-results tr.result', function(e) {
	if (e.target.href === undefined && $(this).data('state') !== 'selected') {
		mailpile.pile_action_select($(this));		
	}
});

$(document).on('click', '#pile-results tr.result-on', function(e) {
	if (e.target.href === undefined && $(this).data('state') === 'selected') {
		mailpile.pile_action_unselect($(this));
	}
});

/* Pile - Show Unread */
$(document).on('click', '.button-sub-navigation', function() {

  var filter = $(this).data('filter');

  $('.sub-navigation ul li').removeClass('navigation-on');
  $(this).parent().addClass('navigation-on');

  if (filter == 'in_unread') {

    $('#display-unread').addClass('navigation-on');
    $('tr').hide('fast', function() {
      $('tr.in_new').show('fast');
    });
  }
  else if (filter == 'in_later') {

    $('#display-later').addClass('navigation-on');
    $('tr').hide('fast', function() {
      $('tr.in_later').show('fast');
    });
  }
  else {

    $('#display-all').addClass('navigation-on');
    $('tr.result').show('fast');
  }

  return false;
});


/* Pile - Change Display Size */
$(document).on('click', 'a.change-view-size', function(e) {

  e.preventDefault();
  var current_size = localStorage.getItem('view_size');
  var change_size = $(this).data('view_size');

  // Update Link Selected
  $('a.change-view-size').removeClass('view-size-selected');
  $(this).addClass('view-size-selected');

  // Update View Sizes
  mailpile.pile_display(current_size, change_size);

  // Data
  localStorage.setItem('view_size', change_size);
});


/* Dragging & Dropping From Pile */
$('td.draggable').draggable({
  containment: "#container",
  appendTo: 'body',
  scroll: false,
  revert: true,
  helper: function(event) {

    var selected_count = parseInt($('#bulk-actions-selected-count').html());

    if (selected_count == 0) {
      drag_count = '1 message</div>';
    }
    else {
      drag_count = selected_count + ' messages';
    }

    return $('<div class="pile-results-drag ui-widget-header"><span class="icon-message"></span> Move ' + drag_count + '</div>');
  },
  stop: function(event, ui) {
    //console.log('done dragging things');
  }
});


$('li.sidebar-tags-draggable').droppable({
  accept: 'td.draggable',
  activeClass: 'sidebar-tags-draggable-hover',
  hoverClass: 'sidebar-tags-draggable-active',
  tolerance: 'pointer',
  drop: function(event, ui) {

    var delete_tag = '';

    if ($.url.segment(0) === 'in') {
     delete_tag = $.url.segment(1);
    }

    // Add MID to Cache
    mailpile.bulk_cache_add(ui.draggable.parent().data('mid'));

    // Add / Delete
    mailpile.tag_add_delete($(this).data('tag_name'), delete_tag, mailpile.bulk_cache, function() {

      // Update Pile View
      $.each(mailpile.bulk_cache, function(key, mid) {
        $('#pile-message-' + mid).fadeOut('fast');
      });

      // Empty Bulk Cache
      mailpile.bulk_cache = [];
    });
  }
});


$(document).ready(function() {

  if (!localStorage.getItem('view_size')) {
    localStorage.setItem('view_size', mailpile.defaults.view_size);
  }

  mailpile.pile_display(localStorage.getItem('view_size'));

  // Display Select
  $.each($('a.change-view-size'), function() {
    if ($(this).data('view_size') == localStorage.getItem('view_size')) {
      $(this).addClass('view-size-selected');
    }
  });
  
  $('.pile-message-tag').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var html = '<div>\
          <h4 class="text-center">' + $(this).data('tag_name') + '\</h4>\
          <p><a class="button-primary" href="' + $(this).data('tag_url') + '"><span class="icon-links"></span> Browse This Tag</a></p>\
          </div>';
        return html;
      }
    },
    style: {
      classes: 'qtip-thread-crypto',
      tip: {
        corner: 'bottom center',
        mimic: 'bottom center',
        border: 0,
        width: 10,
        height: 10
      }
    },
    position: {
      my: 'bottom center',
      at: 'top left',
			viewport: $(window),
			adjust: {
				x: 7,  y: -4
			}
    },
    show: {
      delay: 150
    },
    hide: {
      delay: 1000
    }
  });  

});

/* **********************************************
     Begin search.js
********************************************** */

MailPile.prototype.search = function(q) {
	var that = this;
	$("#search-query").val(q);
	this.json_get("search", {"q": q}, function(data) {
		if ($("#results").length == 0) {
			$("#content").prepend('<table id="results" class="results"><tbody></tbody></table>');
		}
		$("#results tbody").empty();
		for (var i = 0; i < data.results.length; i++) {
			msg_info = data.results[i];
			msg_tags = data.results[i].tags;
			d = new Date(msg_info.date*1000)
			zpymd = d.getFullYear() + "-" + (d.getMonth()+1).pad(2) + "-" + d.getDate().pad(2);
			ymd = d.getFullYear() + "-" + (d.getMonth()+1) + "-" + d.getDate();
			taghrefs = msg_tags.map(function(e){ return '<a onclick="mailpile.search(\'\\' + e + '\')">' + e + '</a>'}).join(" ");
			tr = $('<tr class="result"></tr>');
			tr.addClass((i%2==0)?"even":"odd");
			tr.append('<td class="checkbox"><input type="checkbox" name="msg_' + msg_info.id + '"/></td>');
			tr.append('<td class="from"><a href="' + msg_info.url + '">' + msg_info.from + '</a></td>');
			tr.append('<td class="subject"><a href="' + msg_info.url + '">' + msg_info.subject + '</a></td>');
			tr.append('<td class="tags">' + taghrefs + '</td>');
			tr.append('<td class="date"><a onclick="mailpile.search(\'date:' + ymd + '\');">' + zpymd + '</a></td>');
			$("#results tbody").append(tr);
		}
		that.loglines(data.chatter);
	});
}


MailPile.prototype.focus_search = function() {
	$("#search-query").focus(); return false;
}


MailPile.prototype.results_list = function() {

  // Navigation
	$('#btn-display-list').addClass('navigation-on');
	$('#btn-display-graph').removeClass('navigation-on');
	
	// Show & Hide View
	$('#pile-graph').hide('fast', function() {

    $('#form-pile-results').show('normal');
    $('#pile-results').show('fast');
    $('.pile-speed').show('normal');
    $('#footer').show('normal');
	});
}

$(document).on('click', '#search-query', function() {
  $(this).select();  
});

$(document).ready(function() {

	/* Search Box */
	$('#button-search-options').on("click", function(key) {
		$('#search-params').slideDown('fast');
	});

	$('#button-search-options').on("blur", function(key) {
		$('#search-params').slideUp('fast');
	});
	
});


/* **********************************************
     Begin thread.js
********************************************** */

MailPile.prototype.render_thread_message = function(mid) {
  
  $.ajax({
    url			 : mailpile.api.message + mid + "/single.jhtml",
    type		 : 'GET',
    dataType : 'json',
    success  : function(response) {
      if (response.results) {
        $('#snippet-' + mid).replaceWith(response.results[0]);
      }
    },
    error: function() {
      mailpile.notification('error', 'Could not retrieve message');
    }
  });
};

MailPile.prototype.thread_initialize_tooltips = function() {

  $('.thread-item-crypto-info').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var html = '<div>\
          <h4 class="' + $(this).data('crypto_color') + '">\
            <span class="' + $(this).data('crypto_icon') + '"></span>' + $(this).attr('title') + '\
          </h4>\
          <p>' + $(this).data('crypto_message') + '</p>\
          </div>';
        return html;
      }
    },
    style: {
      classes: 'qtip-thread-crypto',
      tip: {
        corner: 'bottom center',
        mimic: 'bottom center',
        border: 0,
        width: 10,
        height: 10
      }
    },
    position: {
      my: 'bottom center',
      at: 'top left',
			viewport: $(window),
			adjust: {
				x: 7,  y: -4
			}
    },
    show: {
      delay: 150
    },
    hide: {
      delay: 250
    }
  });
};


/* Thread - Show People In Conversation */
$(document).on('click', '.show-thread-people', function() {

 //alert('FIXME: Show all people in conversation');
 var options = {
   backdrop: true,
   keyboard: true,
   show: true,
   remote: false
 };

 $('#modal-full .modal-title').html($('#thread-people').data('modal_title'));
 $('#modal-full .modal-body').html($('#thread-people').html());
 $('#modal-full').modal(options);
});

/* Thread - Show Tags In Converstation */
$(document).on('click', '.show-thread-tags', function() {

 var options = {
   backdrop: true,
   keyboard: true,
   show: true,
   remote: false
 };

 $('#modal-full .modal-title').html($('#thread-tags').data('modal_title'));
 $('#modal-full .modal-body').html($('#thread-tags').html());
 $('#modal-full').modal(options);
});

/* Thread - Show Security */
$(document).on('click', '.show-thread-security', function() {
  
  alert('FIXME: Show details about security of thread');
});

/* Thread - Show Metadata Info */
$(document).on('click', '.show-thread-message-metadata-details', function() {
  $('#metadata-details-' + $(this).parent().parent().parent().parent().data('mid')).fadeIn();
});


/* Thread - Expand Snippet */
$(document).on('click', 'div.thread-snippet', function(e) {  
  var mid = $(this).data('mid');
  if (e.target.href === undefined && $(e.target).data('expand') !== 'no') {
    mailpile.render_thread_message(mid);
  }
});


/* Thread - Message Quote Show */
$(document).on('click', '.thread-item-quote-show', function() {
  var quote_id = $(this).data('quote_id');
  var quote_text = $('#message-quote-text-' + quote_id).html();
  $('#message-quote-' + quote_id).html(quote_text);
});


/* Thread - Might Move to Global Location / Abstraction */
$(document).on('click', '.dropdown-toggle', function() {
  $(this).find('.icon-arrow-right').removeClass('icon-arrow-right').addClass('icon-arrow-down');
});


/* Thread - Add / Update Contact From Signature */
$(document).on('mouseenter', '.thread-item-signature', function() {

  /* Validate "is this a signature" by weights
  *   - Contains same name as in From field
  *   - Has Emails
  *   - Has URLs (does URL match email domain)
  *   - Has Phone numbers
  *   - Has Street addresses
  */
  
  var id = $(this).attr('id');
  var mid = $(this).attr('id').split('-')[2];

  // FIXME: make this determine "Add" or "Update" Contact
  $('#' + id).prepend('<button id="signature-contact-'+ mid +'" class="button-signature-contact"><span class="icon-user"></span> Add</button>').addClass('thread-item-signature-hover');

}).on('mouseleave', '.thread-item-signature', function() {

  var id = $(this).attr('id');
  var mid = $(this).attr('id').split('-')[2];
  $('#signature-contact-'+ mid).remove();
  $('#' + id).removeClass('thread-item-signature-hover');

});

$(document).on('click', '.button-signature-contact', function() {

 var options = {
   backdrop: true,
   keyboard: true,
   show: true,
   remote: false
 };

 $('#modal-full .modal-title').html('Add To Contacts');
 $('#modal-full .modal-body').html('Eventually this feature will auto extract Names, Emails, URLs, Phone Numbers, and Addresses and prepopulate form fields to make contact management easier. Hang in there, its coming ;)');
 $('#modal-full').modal(options);
});



/* Thread Tooltips */
$(document).ready(function() {

  // Thread Scroll to Message
  if (location.href.split("thread/=")[1]) {

    var thread_id = location.href.split("thread/=")[1].split("/")[0];
    var msg_top_pos = $('#message-' + thread_id).position().top;
    $('#content-view').scrollTop(msg_top_pos - 150);
    setTimeout(function(){
      $('#content-view').animate({ scrollTop: msg_top_pos }, 350);
    }, 50);

    mailpile.thread_initialize_tooltips();
  }

});



/* **********************************************
     Begin contacts.js
********************************************** */

MailPile.prototype.contact = function(msgids, tags) {}
MailPile.prototype.addcontact = function(tagname) {}

/* Show Contact Add Form */
$(document).on('click', '#button-contact-add', function(e) {

  e.preventDefault();
  $('#contacts-list').hide();
  $('#contact-add').show();

  $('.sub-navigation ul li').removeClass('navigation-on');
  $(this).parent().addClass('navigation-on');
});


var contactActionSelect = function(item) {

  // Data Stuffs    
  mailpile.bulk_cache_add();

	// Increment Selected
	$('#bulk-actions-selected-count').html(parseInt($('#bulk-actions-selected-count').html()) + 1);


	// Style & Select Checkbox
	item.removeClass('result').addClass('result-on').data('state', 'selected');
};


var contactActionUnselect = function(item) {

  // Data Stuffs    
  mailpile.bulk_cache_remove();

	// Decrement Selected
	var selected_count = parseInt($('#bulk-actions-selected-count').html()) - 1;

	$('#bulk-actions-selected-count').html(selected_count);

	// Hide Actions
	if (selected_count < 1) {

	}

	// Style & Unselect Checkbox
	item.removeClass('result-on').addClass('result').data('state', 'normal');
};


$(document).on('click', '#contacts-list div.boxy', function(e) {
	if (e.target.href === undefined && $(this).data('state') === 'selected') {
		contactActionUnselect($(this));
	}
	else if (e.target.href === undefined) {
		contactActionSelect($(this));
	}
});


/* **********************************************
     Begin tags.js
********************************************** */

MailPile.prototype.tag = function(msgids, tags) {}

MailPile.prototype.tag_add = function(tagname) {}

/* Pile - Tag Add */
MailPile.prototype.tag_add = function(tag_add, mids, complete) {

  $.ajax({
	  url			 : mailpile.api.tag,
	  type		 : 'POST',
	  data     : {
      add: tag_add,
      mid: mids
    },
	  dataType : 'json',
    success  : function(response) {

      if (response.status == 'success') {

       complete();

      } else {
        mailpile.notification(response.status, response.message);
      }
    }
  });
};


MailPile.prototype.tag_add_delete = function(tag_add, tag_del, mids, complete) {
  
	  $.ajax({
	  url			 : mailpile.api.tag,
	  type		 : 'POST',
	  data     : {
      add: tag_add,
      del: tag_del,
      mid: mids
    },
	  dataType : 'json',
    success  : function(response) {

      if (response.status == 'success') {

        complete();

      } else {
        mailpile.notification(response.status, response.message);
      }
    }
  });
};


/* Show Tag Add Form */
$(document).on('click', '#button-tag-add', function(e) {

  e.preventDefault();
  $('#tags-list').hide();
  $('#tags-archived-list').hide();
  $('#tag-add').show();

  $('.sub-navigation ul li').removeClass('navigation-on');
  $(this).parent().addClass('navigation-on');
});


/* API - Tag Add */
$(document).on('submit', '#form-tag-add', function(e) {

  e.preventDefault();
  var tag_data = $('#form-tag-add').serialize();

  $.ajax({
    url: mailpile.api.tag_add,
    type: 'POST',
    data: tag_data,
    dataType : 'json',
    success: function(response) {

      mailpile.notification(response.status, response.message);

      if (response.status === 'success') {
        console.log(response);
      }
    }
  });
});

/* **********************************************
     Begin settings.js
********************************************** */

/* Profile Add */
$(document).on('submit', '#form-profile-add', function(e) {

  e.preventDefault();

  var profile_data = {
    name : $('#profile-add-name').val(),
    email: $('#profile-add-email').val()
  };

  var smtp_route = $('#profile-add-username').val() + ':' + $('#profile-add-password').val() + '@' + $('#profile-add-server').val() + ':' + $('#profile-add-port').val();

  if (smtp_route !== ':@:25') {
    profile_data.route = 'smtp://' + smtp_route;
  }

	$.ajax({
    url      : mailpile.api.settings_add,
		type     : 'POST',
		data     : {profiles: JSON.stringify(profile_data)},
		dataType : 'json',
    success  : function(response) {

      mailpile.notification(response.status, response.message);
      if (response.status === 'success') {
        console.log(response);
      }
    }
	});

});