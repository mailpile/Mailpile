/* Composer - Events */

$(document).on('click', '.compose-contact-find-keys', function() {
  var address = $(this).data('address');
  Mailpile.UI.Modals.CryptoFindKeys({
    query:address
  });
});


$(document).on('click', '.compose-crypto-encryption', function() {

  var mid = $(this).data('mid');
  var status = $('#compose-encryption-' + mid).val();
  var change = '';

  if (status === 'encrypt') {
    change = 'none';
  } else {
    var determine = Mailpile.Composer.Crypto.DetermineEncryption(mid, false);
    change = determine.state;

    // Only show sometimes
    if (_.indexOf(['cannot', 'none'], determine.state) > -1) {
      Mailpile.UI.Modals.ComposerEncryptionHelper(mid, determine);
    }
  }

  Mailpile.Composer.Crypto.EncryptionToggle(change, mid);
  Mailpile.Composer.Tooltips.Encryption();
});


/* Compose - Change Signature Status */
$(document).on('click', '.compose-crypto-signature', function() {

  var mid = $(this).data('mid');
  var status = Mailpile.Composer.Crypto.DetermineSignature(mid);
  var change = '';

  if (status === 'sign') {
    change = 'none';
  } else {
    change = 'sign';
  }
  
  Mailpile.Composer.Crypto.SignatureToggle(change, mid);
  Mailpile.Composer.Tooltips.Signature();
});


/* Compose - Show Cc, Bcc */
$(document).on('click', '.compose-show-field', function(e) {
  $(this).hide();
  var field = $(this).text().toLowerCase();
  var mid = $(this).data('mid');
  $('#compose-' + field + '-html').show().removeClass('hide');

  // Destroy select2
  Mailpile.Composer.Recipients.AddressField('compose-' + field + '-' + mid);
});


$(document).on('click', '.compose-hide-field', function(e) {
  var field = $(this).attr('href').substr(1);
  var mid = $(this).data('mid');
  $('#compose-' + field + '-html').hide().addClass('hide');
  $('#compose-' + field + '-show').fadeIn('fast');

  // Destroy select2
  $('#compose-' + field + '-' + mid).select2('destroy');
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
        Mailpile.Composer.Complete(response.result.thread_ids[0]);
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

    // Instatiate select2
    if ($('#compose-to-' + mid).val()) {
      Mailpile.Composer.Recipients.AddressField('compose-to-' + mid);
    }
    if ($('#compose-cc-' + mid).val()) {
      Mailpile.Composer.Recipients.AddressField('compose-cc-' + mid);
    }
    if ($('#compose-bcc-' + mid).val()) {
      Mailpile.Composer.Recipients.AddressField('compose-bcc-' + mid);
    }

    Mailpile.Composer.Tooltips.ContactDetails();

    $('#compose-details-' + mid).slideDown('fast').removeClass('hide');
    $('#compose-to-summary-' + mid).hide();
    $(this).html('<span class="icon-eye"></span> <span class="text">' + new_message + '</span>');
    $(this).data('message', old_message).attr('data-message', old_message);
  }
  else {
    var old_message = $(this).find('.text').html();
    $('#compose-details-' + mid).slideUp('fast').addClass('hide');
    $('#compose-to-summary-' + mid).show();
    $(this).html(new_message);
    $(this).data('message', old_message).attr('data-message', old_message);
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


$(document).on('click', '.compose-attachment-remove', function(e) {
  Mailpile.Composer.Attachments.Remove($(this).data('mid'), $(this).data('aid'));
});


$(document).on('focus', '.compose-text', function() {
  $(this).autosize();
});


$(document).on('click', '.compose-attach-key', function(e) {
  var mid = $(this).data('mid');
  Mailpile.Composer.Crypto.AttachKey(mid);
});


/* Compose - Quoted Reply */
$(document).on('click', '.compose-apply-quote', function(e) {
  var mid = $(this).data('mid');
  var state = $(this).data('quoted_reply');
  Mailpile.Composer.Body.QuotedReply(mid, state);
});


$(document).on('submit', '#form-compose-quoted-reply', function(e) {
  e.preventDefault();
  var quoted_reply = 'enabled';
  if ($(this).find('input[type=checkbox]').is(':checked')) {
    quoted_reply = 'disabled';
  }
  Mailpile.API.settings_set_post({ 'web.quoted_reply': quoted_reply }, function(result) {
    Mailpile.notification(result);
    $('#modal-full').modal('hide');
  });
});


$(document).on('click', '.encryption-helper-find-key', function(e) {

  e.preventDefault();
  $('#encryption-helper-find-keys').find('.loading').fadeIn();

  // Reset Model
  Mailpile.crypto_keylookup = [];
  
  // Empty Previous Search
  $('#encryption-helper-find-keys').find('ul.result').html('');

  // Show Hidden Items
  _.each($('#encryption-helper-missing-keys li.searchkey-result-item'), function(elem, key) {
    $(elem).show();
  });


  // Data & Things
  var mid = $(this).data('mid');
  var address = $(this).attr('href');

  // Show & Hide
  $('li[address="' + address + '"]').hide();
  $('#encryption-helper-find-keys').find('.color-01-gray-mid').html(address);

  // Go Get Keys
  Mailpile.Crypto.Find.Keys({
    query: address,
    container: '#encryption-helper-find-keys',
    action: 'hide-item',
    complete: function(status) {

      // Hide Loading
      $('#encryption-helper-find-keys').find('.loading').slideUp('fast');

      // Show No Results
      if (status === 'none') {
        $('li[address="' + address + '"]').show();
      } else {
        
        // Tally Total Missing Keys
        var count_missing = [];

        // Check Items
        _.each($('#encryption-helper-missing-keys li.searchkey-result-item'), function(elem, key) {
          count_missing.push($(elem).css('display'));
        });

        // Show "Now Able To Encrypt" Message
        console.log(_.indexOf(count_missing, 'list-item'));
        if (_.indexOf(count_missing, 'list-item') == -1) {
          console.log('yay, all have been searched & imported');

          // Positive Feedback
          $('#modal-full').find('span.icon-lock-open')
            .removeClass('icon-lock-open color-10-orange')
            .addClass('icon-lock-closed color-08-green')
            .html('{{_("Yay, Can Now Encrypt")}}');

          var success_template = _.template($('#template-encryption-helper-complete-message').html());
          var success_html = success_template({ mid: mid });

          $('#modal-full').find('div.modal-body').html(success_html);

          // Hide Missing
          $('#encryption-helper-missing-keys').fadeOut();
        }

      }
    }
  });  

});