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

        // UID Featured Item
        var uid = {
          name: '{{_("No Name")}}',
          email: '{{_("No Email")}}'
        };

        if (key.uids[0].name) {
          uid.name = key.uids[0].name;
        }
        if (key.uids[0].email) {
          uid.email = key.uids[0].email;
        }
        if (key.uids[0].comment) {
          uid.comment = key.uids[0].comment;
        }
      }

      // Key Score
      var score_color = Mailpile.UI.Crypto.ScoreColor(key.score_color);


      // Show View
      var item_data     = _.extend({ score_color: score_color, avatar: avatar, uid: uid, address: options.query, action: options.action }, key);
      var item_template = _.template($('#template-crypto-encryption-key').html());
      items_html += item_template(item_data);
  
      // Set Lookup State (data model)
      var key_data = {fingerprints: key.fingerprint, address: options.query, origins: key.origins };
      Mailpile.crypto_keylookup.push(key_data);
    }
 });

  // Show Results
  $(options.container).find('.result').append(items_html);

  // Tooltips
  Mailpile.Crypto.Tooltips.KeyScore();
};


Mailpile.Crypto.Find.KeysDone = function(options) {

  $(options.container).find('.loading').fadeOut();

  // No Keys Found
  // FIXME: doesn't work for 2nd and third lookups returning empty results
  if (!Mailpile.crypto_keylookup.length) {

    var message_template = _.template($('#template-find-keys-none').html());
    var message_html     = message_template(options);

    // Update UI
    $(options.container).find('.message')
      .html(message_html)
      .removeClass('paragraph-important paragraph-success')
      .addClass('paragraph-alert');
      var status = 'none';

  } else {

    // Update UI
    $(options.container).find('.message')
      .removeClass('paragraph-important paragraph-alert')
      .addClass('paragraph-success');
      var status = 'success';
  }

  // Callback
  options.complete(status);
};


Mailpile.Crypto.Find.KeysError = function(options) {

  // Get Message
  var message_template = _.template($('#template-find-keys-error').html());
  var message_html     = message_template(options);

  // Update UI
  $(options.container).find('.loading')
    .fadeOut();

  setTimeout(function() {
    $(options.container).find('.message')
      .html(message_html)
      .removeClass('paragraph-success paragraph-important paragraph-alert')
      .addClass('paragraph-warning');

    // Callback
    options.complete('none');
  }, 250);
};


/**
 * Performs a lookup for encryption keys and renders UI elements
 * @param {string} options.container - container element of all UI elements
 * @param {string} options.action -  
 * @param {string} options.query - the term to lookup
 * @param {function} options.complete 
 */
Mailpile.Crypto.Find.Keys = function(options) {

  if ($(options.container).hasClass('hide')) {
    $(options.container).fadeIn();
  }

  Mailpile.API.async_crypto_keylookup_get({"address": options.query }, function(data, ev) {

    // Render each result found
    if (data.result) {

      $(options.container).find('.message')
        .html('<span class="icon-key"></span> ' + data.message)
        .removeClass('paragraph-success paragraph-alert')
        .addClass('paragraph-important');

      // Show Result
      Mailpile.Crypto.Find.KeysResult(data, options);

    } else {
      // Show Error (connection down, etc...)
      Mailpile.Crypto.Find.KeysError(options);
    }

    // Running Search
    if (data.runningsearch) {

      var searching_template = _.template($('#template-find-keys-running').html());
      var searching_html     = searching_template(options);
      $(options.container).find('.message').html(searching_html);

    } else {
      Mailpile.Crypto.Find.KeysDone(options);
    }
  });
};