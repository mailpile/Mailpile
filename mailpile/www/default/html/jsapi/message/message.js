/* Message */

Mailpile.Message.AnalyzeMessageInline = function(mid) {
  // Iterate through all plain-text parts of the e-mail
  $('#message-' + mid).find('.thread-item-text').each(function(i, text_part) {
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
      var key_template = _.template($('#template-messsage-inline-pgp-key-import').html());
      var name = Mailpile.instance.metadata[mid].from.fn;
      var import_key_html = key_template({ pgp_key: pgp_key, pgp_href: pgp_href, mid: mid, name: name });
      var new_content = content.replace(pgp_key, import_key_html);
      $(text_part).html(new_content);
    }
  });
};


/* Message -  */
$(document).on('click', '.message-action-reply', function() {
  var mid = $(this).data('mid');
  Mailpile.API.message_reply_post({mid: mid, _output: 'composer.jhtml'}, function(result) {

    $('#message-' + mid).append(result.result);
    var new_mid = $('#message-' + mid).find('.form-compose').data('mid');
    $('#compose-details-' + new_mid).hide();
    $('#compose-to-summary-' + new_mid).show();
    $('#compose-show-details-' + new_mid).show();
  });
});



/* Message - Create forward and go to composer */
$(document).on('click', '.message-action-forward', function() {
  var mid = $(this).parent().parent().data('mid');
  $.ajax({
    url      : '/api/0/message/forward/',
    type     : 'POST',
    data     : { mid: mid, 'atts': true },
    success  : function(response) {
      if (response.status === 'success') {
        window.location.href = Mailpile.urls.message_draft + response.result.created + '/';
      } else {
        Mailpile.notification(response);
      }
    }
  });
});


/* Message - Move message to inbox */
$(document).on('click', '.message-action-inbox', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  Mailpile.API.tag_post({ add: ['inbox'],  del: ['spam', 'trash'], mid: mid}, function() {
    window.location.href = '/in/inbox/';
  });
});


/* Message - Move message to archive */
$(document).on('click', '.message-action-archive', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  Mailpile.API.tag_post({ add: '', del: ['inbox'], mid: mid}, function(response) {
    window.location.href = '/in/inbox/';
  });
});


/* Message - Mark message as spam */
$(document).on('click', '.message-action-spam', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  Mailpile.API.tag_post({ add: ['spam'], del: ['trash', 'inbox'], mid: mid}, function() {
    window.location.href = '/in/inbox/';
  });
});


/* Message - Unthread a message from thread */
$(document).on('click', '.message-action-unthread', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  $.ajax({
    url      : '/api/0/message/unthread/',
    type     : 'POST',
    data     : { mid: mid },
    success  : function(response) {
      if (response.status === 'success') {
        var notification_data     = { url: Mailpile.urls.message_sent + mid + '/' };
        var notification_template = _.template($('#template-thread-notification-unthreaded').html());
        var notification_html     = notification_template(notification_data);
        $('#message-' + mid).removeClass('thread-snippet thread-message')
                            .addClass('thread-notification')
                            .html(notification_html);
      } else {
        Mailpile.notification(response);
      }
    }
  });
});


/* Message - Move a message to trash */
$(document).on('click', '.message-action-trash', function() {
  var mid = $(this).parent().parent().data('mid');
  Mailpile.API.tag_post({ add: ['trash'], del: ['spam', 'inbox'], mid: mid}, function() {
    window.location.href = '/in/inbox/';
  });
});


/* Message - Add Contact */
$(document).on('click', '.message-action-add-contact', function(e) {

  // FIXME: Does not work from Dropdown
  e.preventDefault();
  var mid = $(this).parent().parent().data('mid');
  var modal_data = {
    name: $(this).data('name'),
    address: $(this).data('address'),
    signature: 'FIXME: ' + $('#message-' + mid).find('.thread-item-signature').html(),
    mid: mid
  };

  var modal_template = _.template($("#modal-contact-add").html());
  $('#modal-full').html(modal_template(modal_data));
  $('#modal-full').modal(Mailpile.UI.ModalOptions);
});


/* Message - Unsubscribe */
$(document).on('click', '.message-action-unsubscribe', function(e) {
  e.preventDefault();
  alert('FIXME: this should compose an email to: ' + $(this).data('unsubscribe'));
  //Mailpile.activities.compose($(this).data('unsubscribe'));
});


/* Message - Discover keys */
$(document).on('click', '.message-action-find-keys', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.CryptoFindKeys({
    query: $(this).attr('href')
  });
});


/* Message - Import key from a message */
$(document).on('click', '.message-action-import-key', function() {
  $('#modal-full .modal-title').html('<span class="icon-key"></span> Import Key');
  $('#modal-full .modal-body').html('<p>Eventually this will import a PGP key to a contact.</p>');
  $('#modal-full').modal(Mailpile.UI.ModalOptions);
});


/* Message - Crypto Feedback Actions */
$(document).on('click', '.message-crypto-action', function() {
  Mailpile.API.crypto_gpg_keylist_secret_get({}, function(result) {
    var mid = $(this).data('mid');
    var modal_data = { name: 'User Name', address: 'name@address.org' };
    var modal_template = _.template($("#modal-send-public-key").html());
    $('#modal-full').html(modal_template(modal_data));

    var key_html = '';

    _.each(result.result, function(key) {
      var key_template = _.template($('#template-modal-private-key-item').html());
      key_html +=  key_template(key);
    });

    $('#crypto-private-key-list').html(key_html);

    $('#modal-full').modal(Mailpile.UI.ModalOptions);
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
      var modal_template = _.template($("#modal-search-keyservers").html());
      $('#modal-full').html(modal_template({ keys: '<li>Key of User #1</li>' }));
      $('#modal-full').modal(Mailpile.UI.ModalOptions);
    });
  }
});


$(document).on('click', '.message-crypto-show-inline-key', function() {
  $(this).hide();
  $('#message-crypto-inline-key-' + $(this).data('mid')).fadeIn();
});

