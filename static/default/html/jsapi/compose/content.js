/* Generate New draft MID */
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
};


/* Compose - */
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
};


/* Compose - */
MailPile.prototype.compose_autosave_update_ephemeral = function(mid, new_mid) {

  // Update UI Elements
  $.each($('.has-mid'), function(key, elem) {
    $(this).data('mid', new_mid).attr('data-mid', new_mid);
    if ($(this).attr('id') !== undefined) {
      var new_id = $(this).attr('id').replace(mid, new_mid, "gi");
      $(this).attr('id', new_id);
    }
  });

  $('#compose-mid-' + new_mid).val(new_mid);

  // Remove Ephermal From Model - is added with new MID in mailpile.compose_autosave()
  mailpile.messages_composing = _.omit(mailpile.messages_composing, mid);
};


/* Compose - Perform autosave checking & save */
MailPile.prototype.compose_autosave = function(mid, form_data) {

  // Text is different, run autosave
  if ($('#compose-text-' + mid).val() !== mailpile.messages_composing['compose-text-' + mid]) {

    // UI Feedback
    var autosave_msg = $('#compose-message-autosaving-' + mid).data('autosave_msg');
    $('#compose-message-autosaving-' + mid).html('<span class="icon-compose"></span>' + autosave_msg).fadeIn();

  	$.ajax({
  		url			 : mailpile.api.compose_save,
  		type		 : 'POST',
      timeout  : 15000,
  		data     : form_data,
  		dataType : 'json',
  	  success  : function(response) {

        var new_mid = response.result.message_ids[0];

        // Update ephermal IDs, Message Model, fadeout UI msg
        if (mid !== new_mid) {
          mailpile.compose_autosave_update_ephemeral(mid, new_mid);
        }

        mailpile.messages_composing['compose-text-' + new_mid] = $('#compose-text-' + new_mid).val();

        setTimeout(function() {
          $('#compose-message-autosaving-' + new_mid).fadeOut();
        }, 2000);
      },
      error: function() {
        var autosave_error_msg = $('#compose-message-autosaving-' + mid).data('autosave_error_msg');
        $('#compose-message-autosaving-' + mid).html('<span class="icon-x"></span>' + autosave_error_msg).fadeIn();
      }
  	});
  }
};


/* Compose Autosave - finds each compose form and performs action */
MailPile.prototype.compose_autosave_timer =  $.timer(function() {
  // UNTESTED: should handle multiples in a thread
  $('.form-compose').each(function(key, form) {
    mailpile.compose_autosave($(form).data('mid'), $(form).serialize());
  });
});


/* Compose - Instance of select2 contact selecting */
MailPile.prototype.compose_address_field = function(id) {

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
    formatSelection: function(state, elem) {

      // Add To Model
      mailpile.instance.search_addresses.push(state);

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
  $('#' + id).select2('data', mailpile.compose_analyze_recipients($('#' + id).val()));

  /* On select update encryption state */
  $('#' + id).on('select2-selecting', function(e) {
      var status = mailpile.compose_determine_encryption(e.val);
      mailpile.compose_render_encryption(status);
    }).on('select2-removed', function(e) {
      var status = mailpile.compose_determine_encryption();
      mailpile.compose_render_encryption(status);
  });
};


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
$('#compose-from').keyup(function(e) {
  var code = (e.keyCode ? e.keyCode : e.which);
  if (code === 9 && $('#compose-subject:focus').val() === '') {
  }
});


/* Compose - Quote */
$(document).on('click', '.compose-apply-quote', function(e) {

  e.preventDefault();
  var mid = $(this).parent().parent().data('mid');

  if ($(this).prop('checked')) {
    $('#compose-text-' + mid).val();
  }
  else {
    $('#compose-text-' + mid).val('');
  }

});


/* Compose - Send, Save, Reply */
$(document).on('click', '.compose-action', function(e) {

  e.preventDefault();
  var action = $(this).val();
  var mid = $(this).parent().data('mid');
  var form_data = $('#form-compose-' + mid).serialize();

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
		data     : form_data,
		dataType : 'json',
	  success  : function(response) {
	    // Is A New Message (or Forward)
      if (action === 'send' && response.status === 'success') {
        window.location.href = mailpile.urls.message_sent + response.result.thread_ids[0] + "/";
      }
      // Is Thread Reply
      else if (action === 'reply' && response.status === 'success') {
        mailpile.compose_render_message_thread(response.result.thread_ids[0]);
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
  
  if ($('#compose-details').hasClass('hide')) {
    $(this).addClass('navigation-on');
    $('#compose-details').slideDown('fast').removeClass('hide');
  } else {
    $(this).removeClass('navigation-on');
    $('#compose-details').slideUp('fast').addClass('hide');
  }
});


/* Compose - Sent To Email */
$(document).on('click', '.compose-to-email', function(e) {
  e.preventDefault();
  mailpile.compose({
    to: $(this).data('email')
  });
});


/* Compose - Attachments uploader */
var uploader = function(settings) {

  var dom = {
    uploader: $('#compose-attachments-' + settings.mid),
    uploads: $('#compose-attachments-files-' + settings.mid)
  };

  var upload_image_preview = function(file) {

    var item = $("<li></li>").prependTo(dom.uploads);
    var image = $(new Image()).appendTo(item);

    // Create an instance of the mOxie Image object. This
    // utility object provides several means of reading in
    // and loading image data from various sources.
    // Wiki: https://github.com/moxiecode/moxie/wiki/Image
    var preloader = new mOxie.Image();
    
    // Define the onload BEFORE you execute the load()
    // command as load() does not execute async.
    preloader.onload = function() {
    
        // This will scale the image (in memory) before it
        // tries to render it. This just reduces the amount
        // of Base64 data that needs to be rendered.
        preloader.downsize(100, 100);

        // Now that the image is preloaded, grab the Base64
        // encoded data URL. This will show the image
        // without making an Network request using the
        // client-side file binary.
        image.prop("src", preloader.getAsDataURL());
    };
    
    // Calling the .getSource() on the file will return an
    // instance of mOxie.File, which is a unified file
    // wrapper that can be used across the various runtime
    // Wiki: https://github.com/moxiecode/plupload/wiki/File
    preloader.load(file.getSource());
  };

  var uploader = new plupload.Uploader({
	runtimes : 'html5',
	browse_button : settings.browse_button, // you can pass in id...
	container: settings.container, // ... or DOM Element itself
  drop_element: settings.container,
	url : '/api/0/message/attach/',
  multipart : true,
  multipart_params : {'mid': settings.mid},
  file_data_name : 'file-data',
	filters : {
		max_file_size : '50mb',
		mime_types: [
			{title : "Audio files", extensions : "mp3,aac,flac,wav,ogg,aiff,midi"},
			{title : "Document files", extensions : "pdf,doc,docx,xls"},
			{title : "Image files", extensions : "jpg,gif,png,svg"},
			{title : "Image files", extensions : "mp2,mp4,mov,avi,mkv"},
			{title : "Zip files", extensions : "zip,rar"},
			{title : "Crypto files", extensions : "asc,pub,key"}
		]
	},
  resize: {
    width: '3600',
    height: '3600',
    crop: true,
    quaility: 100
  },
  views: {
    list: true,
    thumbs: true,
    active: 'thumbs'
  },
	init: {
    PostInit: function() {
      $('#compose-attachments-' + settings.mid).find('.compose-attachment-pick').removeClass('hide');
      $('#compose-attachments-' + settings.mid).find('.attachment-browswer-unsupported').addClass('hide');
      uploader.refresh();
    },
    FilesAdded: function(up, files) {
      var start_upload = true;

    	plupload.each(files, function(file) {

        // Show Preview while uploading
        upload_image_preview(file);

        // Add to attachments
        var attachment_html = '<li id="' + file.id + '">' + file.name + ' (' + plupload.formatSize(file.size) + ') <b></b></li>';
    		$('#compose-attachments-files').append(attachment_html);

        console.log(file);

        // Show Warning for 10mb or larger
        if (file.size > 10485760) {
          start_upload = false;
          alert(file.name + ' is ' + plupload.formatSize(file.size) + '. Some people cannot receive attachments that are 10 mb or larger');
        }
    	});

      if (start_upload) {
        uploader.start();
      }
    },
    UploadProgress: function(up, file) {
    	$('#' + file.id).find('b').html('<span>' + file.percent + '%</span>');
    },
    Error: function(up, err) {
      console.log("Error #" + err.code + ": " + err.message);
      $('#' + err.file.id).find('b').html('Failed');
      uploader.refresh();
    }
  }
  });

  return uploader.init();
};


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
    mailpile.compose_load_crypto_states();

    // Instantiate select2
    $('.compose-address-field').each(function(key, elem) {
      mailpile.compose_address_field($(elem).attr('id'));
    });

    // Save Text Composing Objects
    $('.compose-text').each(function(key, elem) {
        mailpile.messages_composing[$(elem).attr('id')] = $(elem).val()
    });

    // Run Autosave
    mailpile.compose_autosave_timer.play();
    mailpile.compose_autosave_timer.set({ time : 20000, autostart : true });

    // Initialize Attachments
    // FIXME: needs dynamic support for multi composers on a page
    $('.compose-attachments').each(function(key, elem) {
      var mid = $(elem).data('mid');
      console.log('js uploader: ' + mid);
      uploader({
        browse_button: 'compose-attachment-pick-' + mid,
        container: 'form-compose-' + mid,
        mid: mid
      });
    });
  }

});