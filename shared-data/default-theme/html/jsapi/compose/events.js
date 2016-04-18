/* Composer - Events */

$(document).on('click', '.compose-contact-find-keys', function() {
  var $elem = $(this);
  var mid = $elem.data('mid');
  var email = $elem.data('email');
  Mailpile.UI.Modals.CryptoFindKeys({
    query: email,
    strict: true,
    imported: function() {
      if (mid) Mailpile.Composer.Crypto.UpdateEncryptionState(mid);
      $('#modal-full').modal('toggle');
    }
  });
});


$(document).on('click', '.compose-crypto-encryption', function() {
  var mid = $(this).data('mid');
  var status = $('#compose-encryption-' + mid).val();
  var can = $('#compose-crypto-encryption-' + mid).data('can');
  var change = '';

  if (status === 'encrypt') {
    change = 'none';
  }
  else if (status === 'cannot' && can) {
    change = 'encrypt';
  }
  else if (status === 'cannot' || !can) {
    change = 'cannot';
    Mailpile.UI.Modals.ComposerEncryptionHelper(mid, {
      state: 'cannot',
      unencryptables: Mailpile.Composer.Crypto.Unencryptables(mid)
    });
  }
  else {
    change = 'encrypt';
  }

  Mailpile.Composer.Crypto.EncryptionToggle(change, mid, 'manual');
  Mailpile.Composer.Tooltips.Encryption();
});


$(document).on('click', '.compose-crypto-signature', function() {

  var mid = $(this).data('mid');
  var status = $('#compose-signature-' + mid).val();
  var change = '';

  if (status === 'sign') {
    change = 'none';
  } else {
    change = 'sign';
  }

  Mailpile.Composer.Crypto.SignatureToggle(change, mid, 'manual');
  Mailpile.Composer.Tooltips.Signature();
});


/* Compose - Show Cc, Bcc */
$(document).on('click', '.compose-show-field', function(e) {
  $(this).hide();
  var field = $(this).text().toLowerCase();
  var mid = $(this).data('mid');
  $('#compose-' + field + '-html').show().removeClass('hide');

  // Configure select2
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
  return Mailpile.Composer.SendMessage(this);
});

Mailpile.Composer.SendMessage = function(send_btn) {
  var $send_btn = $(send_btn);
  var action = $send_btn.val();
  var mid = $send_btn.parent().data('mid');
  var post_send_url = $send_btn.closest('.has-url').data('url');
  var form_data = $('#form-compose-' + mid).serialize();

  if (action === 'send') {
	  var action_url     = Mailpile.api.compose_send;
	  var action_status  = 'success';
	  var action_message = 'Your message was sent <a id="status-undo-link" data-action="undo-send" href="#">undo</a>';
    var done_working = Mailpile.notify_working("{{_('Preparing to send...')|escapejs}}", 100);
  }
  else if (action == 'save') {
	  var action_url     = Mailpile.api.compose_save;
	  var action_status  = 'info';
	  var action_message = 'Your message was saved';
    var done_working = Mailpile.notify_working("{{_('Saving...')|escapejs}}", 500);
  }
  else if (action == 'reply') {
	  var action_url     = Mailpile.api.compose_send;
	  var action_status  = 'success';
	  var action_message = 'Your reply was sent';
    var done_working = Mailpile.notify_working("{{_('Preparing to send...')|escapejs}}", 100);
  }

  // Warn the user if he's trying to go against his own security policies,
  // let him abort... or not.
  if ((action != 'save') && $send_btn.data('crypto-state').match(/conflict/)) {
    if (!confirm($send_btn.data('crypto-reason') + '\n\n' +
                 '{{_("Click OK to send the message anyway.")|escapejs}}')) return;
  }

  // FIXME: Use Mailpile.API instead of this.
	$.ajax({
		url			 : action_url,
		type		 : 'POST',
		data     : form_data,
		dataType : 'json',
	  success  : function(response) {
	    // Is A New Message (or Forward)
      done_working();
      if (action === 'send' && response.status === 'success') {
        if (post_send_url) {
          Mailpile.go(post_send_url + "/" + mid);
        }
        else {
          Mailpile.go(Mailpile.urls.message_sent + response.result.thread_ids[0] + "/");
        }
      }
      // Is Thread Reply
      else if (action === 'reply' && response.status === 'success') {
        Mailpile.Composer.Complete(response.result.thread_ids[0]);
      }
      else if (response.status === 'error' && response.error.locked_keys) {
        Mailpile.auto_modal({
          url: '{{ U("/settings/set/password/?id=") }}' + response.error.locked_keys[0],
          header: 'off',
          callback: function(result) {
            // Let's try that again!
            Mailpile.Composer.SendMessage(send_btn);
          }
        });
      }
      else {
        Mailpile.notification(response);
      }
    },
    error: function() {
      done_working();
      Mailpile.notification({
        status: 'error',
        message: 'Could not ' + action + ' your message'
      });
    }
	});
};


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
  Mailpile.API.message_unthread_post({ mid: mid }, function(response) {
    Mailpile.API.tag_post({
      mid: mid,
      add: 'trash',
      del: ['drafts', 'blank']
    }, function(response_trash) {
      if (response_trash.status === 'success') {
        // FIXME: Make this more intelligent
        Mailpile.go('/in/inbox/');
      }
      else if (response_trash.status === 'success' &&
               Mailpile.instance.state.command_url === '/message/') {
        // FIXME: NOT REACHED
        $('#form-compose-' + mid).removeClass('form-compose clearfix')
                            .addClass('thread-notification')
                            .html($('#template-thread-notification-draft-trash').html());
      } else {
        Mailpile.notification(response_trash.status, response_trash.message);
      }
    });
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
  $('#compose-send-' + mid).show();
  Mailpile.Composer.Crypto.UpdateEncryptionState(mid, function() {});
});


$(document).on('click', '.compose-attachment-remove', function(e) {
  Mailpile.Composer.Attachments.Remove($(this).data('mid'), $(this).data('aid'));
});


$(document).on('focus', '.compose-text', function() {
  autosize($(this));
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
  var mid = $(this).data('mid');
  var address = $(this).data('email');
  Mailpile.crypto_keylookup = [];  // Reset Model

  e.preventDefault();

  // Reset and show progress area...
  //$('#encryption-helper-find-keys').find('ul.result').html('');
  $('#encryption-helper-find-keys').find('.loading').fadeIn();
  $('#encryption-helper-find-keys').find('.color-01-gray-mid').html(address);

  // Hide the list of missing keys, since we don't really handle
  // multiple searches at once.
  $('#encryption-helper-missing-keys').slideUp('slow');
  $('li[address="' + address + '"]').hide();
  //$('#encryption-helper-missing-keys li.searchkey-result-item').show();

  // Go Get Keys
  var find_options = {
    query: address,
    strict: true,
    container: '#encryption-helper-found-keys',
    action: 'hide-item',
    searched: function(status) {
      // Hide loading animation
      $('#encryption-helper-find-keys').find('.loading').slideUp('fast');

      // If nothing was found, bring back the missing key list.
      if (status === 'none' || status === 'error') {
        $('#encryption-helper-missing-keys').slideDown();
        $('li[address="' + address + '"]').show();
      }
    },
    imported: function() {
      Mailpile.Composer.Crypto.UpdateEncryptionState(mid, function() {
        // If the updated state says we can encrypt, then we should make
        // the interface all happy like!
      });

      if (false) {
        // Tally Total Missing Keys
        var count_missing = [];
        _.each($('#encryption-helper-missing-keys li.searchkey-result-item'), function(elem, key) {
          count_missing.push($(elem).css('display'));
        });
        count_missing = _.indexOf(count_missing, 'list-item');

        // Show "Now Able To Encrypt" Message
        console.log('Missing: ' + count_missing);
        if (count_missing < 1) {
          console.log('yay, all have been searched & imported');

          // Positive Feedback
          $('#modal-full').find('span.icon-lock-open')
            .removeClass('icon-lock-open color-10-orange')
            .addClass('icon-lock-closed color-08-green')
            .html('{{_("Yay, Can Now Encrypt")|escapejs}}');

          var success_template = Mailpile.safe_template($('#template-encryption-helper-complete-message').html());
          var success_html = success_template({ mid: mid });

          $('#modal-full').find('div.modal-body').html(success_html);

          // Hide Missing
          $('#encryption-helper-missing-keys').fadeOut();
        }
        else {
          $('#encryption-helper-missing-keys').show();
        }
      }
    },
    error: function() {
      $('#encryption-helper-missing-keys').slideDown();
      $('li[address="' + address + '"]').show();
    }
  };
  Mailpile.Crypto.Find.Keys(find_options);
});


$(document).on('click', '.modal-retry-encryption', function(e) {
  var mid = $(this).data('mid');
  Mailpile.Composer.Crypto.UpdateEncryptionState(mid, function() {
    $('#form-compose-' + mid + ' .compose-crypto-encryption').click();
  });
});
