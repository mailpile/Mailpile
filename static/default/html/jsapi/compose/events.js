/* Composer - Events */

$(document).on('click', '.compose-contact-find-keys', function() {
  var address = $(this).data('address');
  Mailpile.find_encryption_keys(address);
});

$(document).on('click', '.compose-crypto-encryption', function() {
  var status = $('#compose-encryption').val();
  var change = '';
  var mid = $(this).data('mid');

  if (status == 'encrypt') {
    change = 'none';
  } else {
    if (Mailpile.Composer.Crypto.determine_encryption(mid, false) == "encrypt") {
      change = 'encrypt';
    }
  }

  Mailpile.Composer.Crypto.encryption_toggle(change);
  Mailpile.Composer.Tooltips.encryption();
});


/* Compose - Change Signature Status */
$(document).on('click', '.compose-crypto-signature', function() {
  var status = Mailpile.Composer.Crypto.determine_signature();
  var change = '';

  if (status == 'sign') {
    change = 'none';
  } else {
    change = 'sign';
  }

  Mailpile.Composer.Crypto.signature_toggle(change);
  Mailpile.Composer.Tooltips.signature();
});


/* Compose - Show Cc, Bcc */
$(document).on('click', '.compose-show-field', function(e) {
  $(this).hide();
  var field = $(this).text().toLowerCase();
  var mid = $(this).data('mid');
  $('#compose-' + field + '-html').show().removeClass('hide');

  // Destroy select2
  Mailpile.Composer.Recipients.address_field('compose-' + field + '-' + mid);
});


$(document).on('click', '.compose-hide-field', function(e) {
  var field = $(this).attr('href').substr(1);
  var mid = $(this).data('mid');
  $('#compose-' + field + '-html').hide().addClass('hide');
  $('#compose-' + field + '-show').fadeIn('fast');

  // Destroy select2
  $('#compose-' + field + '-' + mid).select2('destroy');
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
        Mailpile.Composer.render_message_thread(response.result.thread_ids[0]);
      }
      else {
        Mailpile.notification(response);
      }
    },
    error: function() {
      Mailpile.notification({ status: 'error', message: 'Could not ' + action + ' your message'});
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
$(document).on('click', 'a', function(e) {
  if ($(this).attr('href').startsWith('mailto:')) {
    e.preventDefault();
    Mailpile.activities.compose($(this).attr('href').replace('mailto:', ''));
  }
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
      Mailpile.API.tag_post({mid: mid, add: 'trash', del: ['drafts', 'blank']}, function(response_trash) {
        if (response_trash.status === 'success' && Mailpile.instance.state.command_url === '/message/draft/') {
          window.location.href = '/in/inbox/';
        }
        else if (response_trash.status === 'success' && Mailpile.instance.state.command_url === '/message/') {
          $('#form-compose-' + mid).removeClass('form-compose clearfix')
                              .addClass('thread-notification')
                              .html($('#template-thread-notification-draft-trash').html());
        } else {
          Mailpile.notification(response_trash.status, response_trash.message);
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
