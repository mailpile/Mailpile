/* Crypto - Try to find keys locally & remotely */
Mailpile.find_encryption_keys = function(query) {

  $("#modal-full").html($("#modal-search-keyservers").html());

  // This used to be called Mailpile.API.async_crypto_keylookup() but was undefined method
  // Also had the arg "allowremote": true which seemed to be trigger a bad variable error
  Mailpile.API.async_crypto_gpg_searchkey_get({"q": query}, function(data, ev) {

    console.log('called crypto_gpg_searchkey');

    if (data.result) {
      var count = _.size(data.result);
      var total = "1 Key";
      if (count > 1) {
        total = count + " Keys";
      }
      $('#modal-full').find('.modal-title .title').html('Found ' + total);
      $('#modal-full').find('.progress-spinner').addClass('hide');
    }

    if (data.runningsearch) {
      console.log('reuningsearch');
      var searching_data = { query: query };
      var searching_html = _.template($("#template-searchkey-running").html(), searching_data);
      $('#modal-full').find('.modal-body').html(searching_html);
    }

    if (ev.flags == "c") {
      $("#modal-search-keyservers-progress").html("");
    }

    // Build HTML Result
    var items_html = '';

    for (item in data.result) {

      var key = data.result[item];
      var avatar   = '/static/img/avatar-default.png';
      var contact  = _.findWhere(Mailpile.instance.addresses, {address: key.uids[0].email});

      if (contact == true && contact.photo !== undefined) {
        var avatar = contact.photo;
      }

      var item_data = {avatar: avatar, uid: key.uids[0], fingerprint: key.fingerprint.split(/(....)/).join(' ')};
      items_html += _.template($('#template-searchkey-result-item').html(), item_data);
    }

    $('#modal-full').find('.modal-body').html('<ul>' + items_html + '</ul>');
  });

  // Show Modal
  $('#modal-full').modal({
    backdrop: true,
    keyboard: true,
    show: true,
    remote: false
  });
};


/* Crypto - Import key from keyserver */
$(document).on('click', '.contact-add-key-item', function() {

  var key_data = { keyid: $(this).data('keyid') };

  $('#contact-search-keyserver-result').html('');

  Mailpile.API.async_crypto_gpg_receivekey_post({}, function() {
    $('#contact-add-key').html('<span class="icon-key"></span> Encryption Key: ' + key_data.keyid);
    if (response.status === 'success') {
      $('#contact-search-keyserver-result').html('w00t, something here will happen with this key: ' + response.result);
    } else {
      $('#contact-search-keyserver-result').html('Oopsie daisy something is rotten in Denmark :(');
    }
  });
});


/* Crypto -  */
$(document).on('click', '#button-contact-search-keyserver', function(e) {

  e.preventDefault();

  
});