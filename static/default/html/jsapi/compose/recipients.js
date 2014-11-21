/* Composer - Recipients */

Mailpile.Composer.Recipients.AnalyzeAddress = function(address) {
  var check = address.match(/([^<]+?)\s<(.+?)(#[a-zA-Z0-9]+)?>/);

  if (check) {
    if (check[3]) {
      return {"id": check[2], "fn": $.trim(check[1]), "address": check[2], "keys": [{ "fingerprint": check[3].substring(1) }], "flags": { "secure" : true } };
    }
    return {"id": check[2], "fn": $.trim(check[1]), "address": check[2], "flags": { "secure" : false } };
  } else {
    return {"id": address, "fn": address, "address": address, "flags": { "secure" : false }};
  }
};


/* Composer - tokenize input field (to: cc: bcc:) */
Mailpile.Composer.Recipients.Analyze = function(addresses) {

  var existing = [];

  // Is Valid & Has Multiple
  if (addresses) {

    // FIXME: Only solves the comma specific issue. We should do a full RFC 2822 solution eventually.
    var multiple = addresses.split(/>, */);
    var tail = '';

    // Has Multiple
    if (multiple.length > 1) {

      $.each(multiple, function(key, value){
        // Check for <
        if (value.indexOf('<') > -1) {
          tail = '>';
        }
        existing.push(Mailpile.Composer.Recipients.AnalyzeAddress(value + tail)); // Add back on the '>' since the split pulled it off.
      });
    } else {
      if (multiple[0].indexOf('<') > -1) {
        tail = '>';
      }
      existing.push(Mailpile.Composer.Recipients.AnalyzeAddress(multiple[0] + tail));
    }

    return existing;
  }
};


/* Composer - instance of select2 */
Mailpile.Composer.Recipients.AddressField = function(id) {

  // Get MID
  var mid = $('#'+id).data('mid');

  //
  $('#' + id).select2({
    id: function(object) {
      if (object.flags.secure) {
        address = object.address + '#' + object.keys[0].fingerprint;
      } else {
        address = object.address;
      }
      if (object.fn !== "" && object.address !== object.fn) {
        return object.fn + ' <' + address + '>';
      } else {
        return address;
      }
    },
    ajax: { // instead of writing the function to execute the request we use Select2's convenient helper
      url: Mailpile.api.contacts,
      quietMillis: 1,
      cache: true,
      dataType: 'json',
      data: function(term, page) {
        return {
          q: term
        };
      },
      results: function(response, page) { // parse the results into the format expected by Select2
        return {
          results: response.result.addresses
        };
      }
    },
    multiple: true,
    allowClear: true,
    width: '100%',
    minimumInputLength: 1,
    minimumResultsForSearch: -1,
    placeholder: 'Type to add contacts',
    maximumSelectionSize: 100,
    tokenSeparators: [", ", ";"],
    createSearchChoice: function(term) {
      // Check if we have an RFC5322 compliant e-mail address
      if (term.match(/(?:[a-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+\/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])/)) {
        return {"id": term, "fn": term, "address": term, "flags": { "secure" : false }};
      }
    },
    formatResult: function(state) {
      var avatar = '<span class="icon-user"></span>';
      var secure = '';
      if (state.photo) {
        avatar = '<img src="' + state.photo + '">';
      }
      if (state.flags.secure) {
        secure = '<span class="icon-lock-closed"></span>';
      }
      return '<span class="compose-select-avatar">' + avatar + '</span>\
              <span class="compose-select-name">' + state.fn + secure + '<br>\
              <span class="compose-select-address">' + state.address + '</span>\
              </span>';
    },
    formatSelection: function(state, elem) {

      // Add To Model
      var contact_data = _.findWhere(Mailpile.instance.addresses, {address: state.address });
      if (!contact_data) {
        Mailpile.instance.addresses[Math.random().toString(16).substring(6)] = state;
      } else {
        state = contact_data;
      }

      // Create HTML
      var avatar = '<span class="avatar icon-user" data-address="' + state.address + '"></span>';
      var name   = state.fn;
      var secure = '';

      if (state.photo) {
        avatar = '<span class="avatar"><img src="' + state.photo + '" data-address="' + state.address + '"></span>';
      }
      if (!state.fn) {
        name = state.address;
      }
      if (state.flags.secure) {
        secure = '<span class="icon-lock-closed" data-address="' + state.address + '"></span>';
      }

      return avatar + ' <span class="compose-choice-name" data-address="' + state.address + '">' + name + secure + '</span>';
    },
    formatSelectionTooBig: function() {
      return 'You\'ve added the maximum contacts allowed, to increase this go to <a href="#">settings</a>';
    },
    selectOnBlur: true

  }).on('select2-selecting', function(e) {

    /* On select update encryption state */
    var determine = Mailpile.Composer.Crypto.DetermineEncryption(mid, e.val);
    Mailpile.Composer.Crypto.EncryptionToggle(determine.state, mid);

    setTimeout(function() {
      Mailpile.Composer.Tooltips.ContactDetails();
    }, 350);

  }).on('select2-removed', function(e) {
    var determine = Mailpile.Composer.Crypto.DetermineEncryption(mid, false);
    Mailpile.Composer.Crypto.EncryptionToggle(determine.state, mid);
  });

  /* Check encryption state */
  $('#'+id).select2('data', Mailpile.Composer.Recipients.Analyze($('#' + id).val()));

};