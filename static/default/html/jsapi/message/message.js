/* Message - Get new messsage  */
Mailpile.get_new_messages = function(actions) {    
  $.ajax({
	  url			 : Mailpile.api.search_new,
	  type		 : 'GET',
	  dataType : 'json',
    success  : function(response) {
      if (response.status == 'success') {
        actions(response);
      }
    }
  });
};


/* Message - Create forward and go to composer */
$(document).on('click', '.message-action-forward', function() {
  var mid = $(this).parent().parent().data('mid');
  $.ajax({
    url      : '/api/0/message/forward/',
    type     : 'POST',
    data     : { mid: mid },
    success  : function(response) {
      if (response.status === 'success') {
        window.location.href = Mailpile.urls.message_draft + response.result.created + '/';
      } else {
        Mailpile.notification(response.status, response.message);
      }
    }
  });
});


/* Message - Move message to inbox */
$(document).on('click', '.message-action-inbox', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  Mailpile.tag_add_delete(['inbox'], ['spam', 'trash'], mid, function() {
    window.location.href = '/in/inbox/';
  });
});


/* Message - Move message to archive */
$(document).on('click', '.message-action-archive', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  Mailpile.tag_add_delete('', ['inbox'], mid, function(response) {
    window.location.href = '/in/inbox/';
  });
});


/* Message - Mark message as spam */
$(document).on('click', '.message-action-spam', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  Mailpile.tag_add_delete(['spam'], ['trash', 'inbox'], mid, function() {
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
        var notification_data = { url: Mailpile.urls.message_sent + mid + '/' };
        $('#message-' + mid).removeClass('thread-snippet thread-message')
                            .addClass('thread-notification')
                            .html(_.template($('#template-thread-notification-unthreaded').html(), notification_data));
      } else {
        Mailpile.notification(response.status, response.message);
      }
    }
  });
});


/* Message - Move a message to trash */
$(document).on('click', '.message-action-trash', function() {
  var mid = $(this).parent().parent().data('mid');
  Mailpile.tag_add_delete(['trash'], ['spam', 'inbox'], mid, function() {
    window.location.href = '/in/inbox/';
  });
});


/* Message - Add Contact */
$(document).on('click', '.message-action-add-contact', function(e) {

  e.preventDefault();
  var mid = $(this).parent().parent().data('mid');
  var name = $(this).data('name');
  var address = $(this).data('address');
  var signature = 'FIXME: ' + $('#message-' + mid).find('.thread-item-signature').html();

  var modal_html = $("#modal-contact-add").html();
  $('#modal-full').html(_.template(modal_html, {}));
  $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });

  // Add Values
  $('.contact-add-name').val(name);
  $('.contact-add-email').val(address);
  $('.contact-add-signature').html(signature);
  $('.contact-add-mid').val(mid);
});


/* Message - Discover keys */
$(document).on('click', '.message-action-find-keys', function(e) {
  e.preventDefault();
  Mailpile.find_encryption_keys($(this).attr('href'));
});


/* Message - Import key from a message */
$(document).on('click', '.message-action-import-key', function() {

  var options = {
    backdrop: true,
    keyboard: true,
    show: true,
    remote: false
  };

  $('#modal-full .modal-title').html('<span class="icon-key"></span> Import Key');
  $('#modal-full .modal-body').html('<p>Eventually this will import a PGP key to a contact.</p>');
  $('#modal-full').modal(options);
});


/* Message - Crypto Feedback Actions */
$(document).on('click', '.message-crypto-action', function() {
  Mailpile.API.crypto_gpg_keylist_secret_get({}, function(result) {
    var mid = $(this).data('mid');
    var modal_html = $("#modal-send-public-key").html();
    var modal_data = { name: 'User Name', address: 'name@address.org' };
    $('#modal-full').html(_.template(modal_html, modal_data));

    var key_html = '';

    _.each(result.result, function(key) {
      key_html += _.template($('#template-modal-private-key-item').html(), key);
    });

    $('#crypto-private-key-list').html(key_html);

    $('#modal-full').modal({
      backdrop: true,
      keyboard: true,
      show: true,
      remote: false
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
      var modal_html = $("#modal-search-keyservers").html();
      $('#modal-full').html(_.template(modal_html, { keys: '<li>Key of User #1</li>' }));
      $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
    });     
  }
});

