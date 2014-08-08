/* Crypto - Render results from Mailpile.find_encryption_keys() */
Mailpile.render_find_encryption_keys_found = function(data, query) {

  var items_html = '';

  _.each(data.result, function(key) {

    // Loop through UIDs for match to Query
    var uid = _.findWhere(key.uids, {email: query});

    console.log('DA UID');
    console.log(uid);

    // Try to find Avatar
    if (uid) {

      var contact  = _.findWhere(Mailpile.instance.addresses, {address: uid.email});
      console.log();
      var avatar   = '/static/img/avatar-default.png';

      if (contact == true && contact.photo !== undefined) {
        avatar = contact.photo;
        console.log(avatar);
      }
    }

    var item_data = _.extend({avatar: avatar, uid: uid}, key);

    items_html += _.template($('#template-searchkey-result-item').html(), item_data);
  })

  $('#modal-full').find('.modal-body').data('result', '').html('<ul>' + items_html + '</ul>');

  // Set Lookup State
  this.crypto_keylookup = 'results';
};

Mailpile.render_find_encryption_keys_done = function(query) {
  
  if (this.crypto_keylookup !== 'results') {
    $('#modal-full').find('.modal-body').html('<p>Sorry, we could not find any encryption keys for the email address: <strong>' + query + '</strong></p>');
  }
};


/* Crypto - Try to find keys locally & remotely */
Mailpile.find_encryption_keys = function(query) {

  $('#modal-full').html($('#modal-search-keyservers').html());

  Mailpile.API.async_crypto_keylookup_get({"address": query }, function(data, ev) {

    // Render each result found
    if (data.result) {

      $('#modal-full').find('.modal-title .title').html(data.message);
      $('#modal-full').find('.progress-spinner').addClass('hide');

      Mailpile.render_find_encryption_keys_found(data, query);
    }

    // Running Search
    if (data.runningsearch) {
      // Wire in UI feedback updates like this:
      // data.result.runningsearch: PGP Keyservers ?
      var searching_data = { query: query };
      var searching_html = _.template($("#template-searchkey-running").html(), searching_data);
      $('#modal-full').find('.modal-body').html(searching_html);
    }
    else {
      Mailpile.render_find_encryption_keys_done(query);
    }

  });

  // Show Modal
  $('#modal-full').modal({
    backdrop: true,
    keyboard: true,
    show: true,
    remote: false
  });
};


/* Crypto - Import Key */
$(document).on('click', '.crypto-key-import', function(e) {

  e.preventDefault();
  var keydata = $(this).data('fingerprint');
  Mailpile.API.async_crypto_keyimport_post(key_data, function(data, ev) {

    console.log('inside of crypto_gpg_receivekey_post');
    console.log(data);

    if (response.status === 'success') {
      $('#contact-search-keyserver-result').html('w00t, something here will happen with this key: ' + response.result);
    } else {
      $('#contact-search-keyserver-result').html('Oopsie daisy something is rotten in Denmark :(');
    }

  });
});


/* Crypto - Key Use */
$(document).on('change', '.crypto-key-policy', function() {
  
  alert('Change Key Policy to: ' + $(this).val() + ' for fingerprint: ' + $(this).data('fingerprint'));

});
