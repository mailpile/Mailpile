/* message.js */

$(document).on('click', '.message-action-forward', function() {
  var mid = $(this).parent().parent().data('mid');
  $.ajax({
    url      : '/api/0/message/forward/',
    type     : 'POST',
    data     : { mid: mid },
    success  : function(response) {
      if (response.status === 'success') {
        window.location.href = mailpile.urls.message_draft + response.result.created + '/';
      } else {
        mailpile.notification(response.status, response.message);
      }
    }
  });
});

$(document).on('click', '.message-action-inbox', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  mailpile.tag_add_delete(['inbox'], ['spam', 'trash'], mid, function(result) {
    window.location.href = '/in/inbox/';
  });
});

$(document).on('click', '.message-action-spam', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  mailpile.tag_add_delete(['spam'], ['trash', 'inbox'], mid, function() {
    window.location.href = '/in/inbox/';
  });
});

$(document).on('click', '.message-action-unthread', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  $.ajax({
    url      : '/api/0/message/unthread/',
    type     : 'POST',
    data     : { mid: mid },
    success  : function(response) {
      if (response.status === 'success') {
        window.location.href = mailpile.urls.message_sent + mid + '/';
      } else {
        mailpile.notification(response.status, response.message);
      }
    }
  });
});

$(document).on('click', '.message-action-trash', function() {
  var mid = $(this).parent().parent().data('mid');
  mailpile.tag_add_delete(['trash'], ['spam', 'inbox'], mid, function() {
    window.location.href = '/in/inbox/';
  });
});


/* Message - Crypto Feedback Actions */
$(document).on('click', '.message-crypto-action', function() {

  var mid = $(this).data('mid');

  var modal_html = $("#modal-send-public-key").html();
  $('#modal-full').html(_.template(modal_html, { name: 'User Name', address: 'name@address.org' }));
  $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
});


$(document).on('click', '.message-crypto-investigate', function() {

  var mid = $(this).data('mid');
  var part = $(this).data('part');
  var message = mailpile.instance.messages[mid];
  var missing_keys = message.text_parts[part].crypto.encryption.missing_keys;

  // Search Keyservers Missing Keys
  if (missing_keys.length) {
    // FIXME: this needs to search all "missing_key" values
    // this is tricky as searching multiple calls to keyservers
    // can have much latency and slowness
    new_mailpile.api.crypto_gpg_searchkey(missing_keys[0], function(data) {
      var modal_html = $("#modal-search-keyservers").html();
      $('#modal-full').html(_.template(modal_html, { keys: '<li>Key of User #1</li>' }));
      $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
    });     
  }
});