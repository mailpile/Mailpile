/* Crypto - Render results from Mailpile.find_encryption_keys() */
Mailpile.render_find_encryption_keys_found = function(data, query) {

  var items_html = '';

  _.each(data.result, function(key) {

    // Loop through UIDs for match to Query
    var uid = _.findWhere(key.uids, {email: query});

    // Try to find Avatar
    if (uid) {

      var contact  = _.findWhere(Mailpile.instance.addresses, {address: uid.email});
      var avatar   = '/static/img/avatar-default.png';

      if (contact) {
        if (contact.photo) {
          avatar = contact.photo;
        }
      }
    }

    // Show View
    var item_data = _.extend({avatar: avatar, uid: uid, address: query}, key);
    items_html += _.template($('#template-searchkey-result-item').html(), item_data);
 
    // Set Lookup State (data model)
    var key_data = {fingerprints: key.fingerprint, address: query, origins: key.origins };
    Mailpile.crypto_keylookup.push(key_data);
 });

  $('#modal-full').find('.modal-body').data('result', '').html('<ul>' + items_html + '</ul>');
};


Mailpile.render_find_encryption_keys_done = function(query) {
  $('#modal-full').find('.progress-spinner').addClass('hide');
  if (!this.crypto_keylookup.length) {
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
      Mailpile.render_find_encryption_keys_found(data, query);
    }

    // Running Search
    if (data.runningsearch) {
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
  var key_data = _.findWhere(Mailpile.crypto_keylookup, {fingerprints: $(this).data('fingerprint')});
  Mailpile.API.crypto_keyimport_post(key_data, function(result) {
    $('#modal-full').modal('hide');
  });
});


/* Crypto - Key Use */
$(document).on('change', '.crypto-key-policy', function() {
  
  alert('Change Key Policy to: ' + $(this).val() + ' for fingerprint: ' + $(this).data('fingerprint'));

});
