/* Crypto - Find */


Mailpile.Crypto.Find.KeysResult = function(data, options) {

  var items_html = '';

  _.each(data.result, function(key) {

    if (!$('#item-encryption-key-' + key.fingerprint).length) {

      // Loop through UIDs for match to Query
      var uid = _.findWhere(key.uids, {email: options.query});
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
      var item_data = _.extend({ avatar: avatar, uid: uid, address: options.query }, key);
      var item_template = _.template($('#template-crypto-item-encryption-key').html());
      items_html += item_template(item_data);
  
      // Set Lookup State (data model)
      var key_data = {fingerprints: key.fingerprint, address: options.query, origins: key.origins };
      Mailpile.crypto_keylookup.push(key_data);

    }

 });

  // Show Results
  $(options.result).append(items_html);
};


Mailpile.Crypto.Find.KeysDone = function(options) {

  $('#search-keyservers-progress').addClass('hide');

  if (!Mailpile.crypto_keylookup.length) {
    $(options.message)
      .html('<span class="icon-x"></span> No encryption keys found matching: ' + options.query)
      .removeClass('paragraph-important paragraph-success')
      .addClass('paragraph-alert');
    $(options.result).html('');
  } else {
    $(options.message)
      .removeClass('paragraph-important paragraph-alert')
      .addClass('paragraph-success');
  }
};


Mailpile.Crypto.Find.Keys = function(options) {

  if ($(options.container).hasClass('hide')) {
    $(options.container).fadeIn();
  }

  Mailpile.API.async_crypto_keylookup_get({"address": options.query }, function(data, ev) {

    // Render each result found
    if (data.result) {
      $(options.message).html('<span class="icon-checkmark"></span> ' + data.message)
        .removeClass('paragraph-success paragraph-alert')
        .addClass('paragraph-important');
      Mailpile.Crypto.Find.KeysResult(data, options);
    }

    // Running Search
    if (data.runningsearch) {
      var searching_template = _.template($("#template-searchkey-running").html());
      var searching_html = searching_template({ query: options.query });
      $(options.message).html(searching_html);
    }
    else {
      Mailpile.Crypto.Find.KeysDone(options);
    }
  });

};