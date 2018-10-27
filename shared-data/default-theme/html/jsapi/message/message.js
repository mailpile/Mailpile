/* Message */

Mailpile.Message.AnalyzeMessageInline = function(mid) {
  // Iterate through all plain-text parts of the e-mail
  $('#message-' + mid).find('.message-part-text').each(function(i, text_part) {
    var content = $(text_part).html();

    // Check & Extract Inline PGP Key
    var pgp_begin = '-----BEGIN PGP PUBLIC KEY BLOCK-----';
    var pgp_end = '-----END PGP PUBLIC KEY BLOCK-----';
    var check_inline_pgp_key = content.split(pgp_begin);
    if (check_inline_pgp_key.length > 1) {
      var pgp_key = check_inline_pgp_key.slice(1).join().split(pgp_end)[0];
      pgp_key = pgp_begin + pgp_key + pgp_end;

      // Make HTML5 download href
      var pgp_href = 'data:application/pgp-keys;charset=ascii,' + encodeURIComponent(pgp_key.replace(/<\/?[^>]+(>|$)/g, ''));

      // Replace Text
      // FIXME: Unsafe template, please audit
      var key_template = Mailpile.unsafe_template($('#template-messsage-inline-pgp-key-import').html());
      var name = Mailpile.instance.metadata[mid].from.fn;
      var import_key_html = key_template({ pgp_key: pgp_key, pgp_href: pgp_href, mid: mid, name: name });
      var new_content = content.replace(pgp_key, import_key_html);
      $(text_part).html(new_content);
    }
  });
};


/* Message - Replies  */
Mailpile.Message.DoReply = function(mids, reply_all) {
  var mid = undefined;
  $.each(mids, function() {
    if ($('.pile-message-' + this + ' .message-container').length) mid = this;
  });

  var args = {
    mid: mids,
    reply_all: (reply_all == 'all') ? 'True' : 'False',
  };
  if (mid) args['_output'] = 'composer.jhtml!minimal'

  Mailpile.API.message_reply_post(args, function(response) {
    if (mid) {
      var $msg = $('#message-' + mid);
      if ($msg.hasClass('pile-message')) {
        $msg.closest('td').html(response.result);
      }
      else {
        $msg.append(response.result);
        var new_mid = $msg.find('.form-compose').data('mid');
        $('#compose-details-' + new_mid).hide();
        $('#compose-to-summary-' + new_mid).show();
        $('#compose-show-details-' + new_mid).show();
      }
    }
    else {
      Mailpile.go(Mailpile.urls.message_draft + response.result.created + '/');
    }
  });
};
$(document).on('click', '.message-action-reply-all', function(e) {
  e.preventDefault();
  Mailpile.Message.DoReply([$(this).closest('.has-mid').data('mid')], 'all');
});
$(document).on('click', '.message-action-reply', function(e) {
  e.preventDefault();
  Mailpile.Message.DoReply([$(this).closest('.has-mid').data('mid')]);
});


/* Message - Create forward and go to composer */
Mailpile.Message.DoForward = function(mids) {
  Mailpile.API.message_forward_post({
    mid: mids,
    atts: true
  }, function(response) {
    Mailpile.go(Mailpile.urls.message_draft + response.result.created + '/');
  });
};
$(document).on('click', '.message-action-forward', function(e) {
  e.preventDefault();
  Mailpile.Message.DoForward([$(this).closest('.has-mid').data('mid')]);
});


/* Message - Move message to inbox */
$(document).on('click', '.message-action-inbox', function(e) {
  e.preventDefault();
  var mid = $(this).closest('.has-mid').data('mid');
  Mailpile.API.tag_post({ add: ['inbox'],  del: ['spam', 'trash'], mid: mid}, function() {
    Mailpile.go('/in/inbox/');
  });
});


/* Message - Move message to archive */
$(document).on('click', '.message-action-archive', function() {
  var mid = $(this).closest('.has-mid').data('mid');
  Mailpile.API.tag_post({ add: '', del: ['inbox'], mid: mid}, function(response) {
    Mailpile.go('/in/inbox/');
  });
});


/* Message - Mark message as spam */
$(document).on('click', '.message-action-spam', function() {
  var mid = $(this).closest('.has-mid').data('mid');
  Mailpile.API.tag_post({ add: ['spam'], del: ['trash', 'inbox'], mid: mid}, function() {
    Mailpile.go('/in/inbox/');
  });
});


/* Message - Move a message to trash */
$(document).on('click', '.message-action-trash', function() {
  var mid = $(this).closest('.has-mid').data('mid');
  Mailpile.API.tag_post({ add: ['trash'], del: ['spam', 'inbox'], mid: mid},
                        function() {
    Mailpile.go('/in/inbox/');
  });
});


/* Message - Add Contact */
$(document).on('click', '.message-action-add-contact', function(e) {

  // FIXME: Does not work from Dropdown
  e.preventDefault();
  var mid = $(this).closest('.has-mid').data('mid');
  var modal_data = {
    name: $(this).data('name'),
    address: $(this).data('address'),
    signature: 'FIXME: ' + $('#message-' + mid).find('.message-part-signature').html(),
    mid: mid
  };

  Mailpile.API.with_template('modal-contact-add', function(modal) {
    Mailpile.UI.show_modal(modal(modal_data));
  });
});


/* Message - Unsubscribe */
$(document).on('click', '.message-action-unsubscribe', function(e) {
  e.preventDefault();
  alert('FIXME: this should compose an e-mail to: ' + $(this).data('unsubscribe'));
  //Mailpile.activities.compose($(this).data('unsubscribe'));
});


/* Message - Discover keys */
$(document).on('click', '.message-action-find-keys', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.CryptoFindKeys({
    query: $(this).data('email')
  });
});


/* Message - Crypto Feedback Actions */
$(document).on('click', '.message-crypto-action', function() {
  Mailpile.API.crypto_gpg_keylist_secret_get({}, function(result) {
    var mid = $(this).data('mid');
    var modal_data = { name: 'User Name', address: 'name@address.org' };
    Mailpile.API.with_template('modal-send-public-key', function(modal) {
      var key_html = '';
      _.each(result.result, function(key) {
        var key_template = Mailpile.safe_template($('#template-modal-private-key-item').html());
        key_html += key_template(key);
      });

      $('#modal-full').html(modal(modal_data));
      $('#crypto-private-key-list').html(key_html);
      Mailpile.UI.show_modal();
    });
  });
});


/* Message - Investigate a message with error or missing crypto state */
$(document).on('click', '.message-crypto-investigate', function() {

  var mid = $(this).data('mid');
  var part = $(this).data('part');
  var message = Mailpile.instance.messages[mid];
  var missing_keys = message.text_parts[part].crypto.encryption.missing_keys;

  // Search Keyservers Missing Keys
  if (missing_keys.length) {
    // FIXME: this needs to search all "missing_key" values
    // this is tricky as searching multiple calls to keyservers
    // can have much latency and slowness
    Mailpile.API.crypto_gpg_searchkey_get(missing_keys[0], function(data) {
      // FIXME: Unsafe template, please audit
      var modal_template = Mailpile.unsafe_template($("#modal-search-keyservers").html());
      Mailpile.UI.show_modal(modal_template({
        keys: '<li>Key of User #1</li>'
      }));
    });
  }
});


$(document).on('click', '.message-crypto-show-inline-key', function() {
  $(this).hide();
  $('#message-crypto-inline-key-' + $(this).data('mid')).fadeIn();
});
