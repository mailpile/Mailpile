/* Crypto - Render results from Mailpile.UI.Modals.CryptoFindKeys() */
Mailpile.UI.Modals.CryptoFindKeysResult = function(data, query) {

  var items_html = '';

  _.each(data.result, function(key) {

    // Loop through UIDs for match to Query
    var uid = _.findWhere(key.uids, {email: query});
    var avatar   = '/static/img/avatar-default.png';

    // Try to find Avatar
    if (uid) {
      var contact  = _.findWhere(Mailpile.instance.addresses, {address: uid.email});
      if (contact) {
        if (contact.photo) {
          avatar = contact.photo;
        }
      }
    } else {
      var uid = {
        name: '{{_("No Name")}}',
        email: '{{_("No Email")}}',
        note: ''
      };
    }

    // Show View
    var item_data = _.extend({avatar: avatar, uid: uid, address: query}, key);
    var item_template = _.template($('#template-searchkey-result-item').html());
    items_html += item_template(item_data);

    // Set Lookup State (data model)
    var key_data = {fingerprints: key.fingerprint, address: query, origins: key.origins };
    Mailpile.crypto_keylookup.push(key_data);
 });

  $('#modal-full').find('.modal-body').data('result', '').html('<ul>' + items_html + '</ul>');
};


Mailpile.UI.Modals.CryptoFindKeysDone = function(query) {
  $('#modal-full').find('.progress-spinner').addClass('hide');
  if (!Mailpile.crypto_keylookup.length) {
    $('#modal-full').find('.modal-body').html('<p>Sorry, we could not find any encryption keys for the email address: <strong>' + query + '</strong></p>');
  }
};


/* Crypto - Try to find keys locally & remotely */
Mailpile.UI.Modals.CryptoFindKeys = function(query) {

  $('#modal-full').html($('#modal-search-keyservers').html());

  Mailpile.API.async_crypto_keylookup_get({"address": query }, function(data, ev) {

    // Render each result found
    if (data.result) {
      $('#modal-full').find('.modal-title .title').html(data.message);
      Mailpile.UI.Modals.CryptoFindKeysResult(data, query);
    }

    // Running Search
    if (data.runningsearch) {
      var searching_data = { query: query };
      var searching_template = _.template($("#template-searchkey-running").html());
      var searching_html = searching_template(searching_data);
      $('#modal-full').find('.modal-body').html(searching_html);
    }
    else {
      Mailpile.UI.Modals.CryptoFindKeysDone(query);
    }
  });

  // Show Modal
  $('#modal-full').modal(Mailpile.UI.ModalOptions);
};


