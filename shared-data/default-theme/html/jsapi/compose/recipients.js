/* Composer - Recipients */

Mailpile.Composer.Recipients.Get = function(mid, which) {
  var $elem = $('#compose-' + which + '-' + mid);
  return Mailpile.Composer.Recipients.Analyze($elem.val());
};


Mailpile.Composer.Recipients.WithToCcBcc = function(mid, callback) {
  var fields = ['to', 'cc', 'bcc'];
  for (var i in fields) {
    var rcpts = Mailpile.Composer.Recipients.Get(mid, fields[i]);
    callback(fields[i], rcpts);
  }
};


Mailpile.Composer.Recipients.GetAll = function(mid, filter) {
  var recipients = [];
  Mailpile.Composer.Recipients.WithToCcBcc(mid, function(field, rcpts) {
    for (var j in rcpts) {
      recipients.push(filter ? filter(rcpts[j]) : rcpts[j]);
    }
  });
  return recipients;
};


Mailpile.Composer.Recipients.AnalyzeAddress = function(address, preset) {
  /* The Mailpile API guarantees consistent formatting of addresses, so
     a simple regexp should generally work juuuust fine. However, we also
     want to handle pasted or typed input. So we try the simple parse first,
     and then get a bit more creative. */
  var check = address.match(/^\s*([^<]*?)\s*<?([^\s<>]+@[^\s<>#]+)(#[a-zA-Z0-9]+)?>?\s*$/);
  if (!check) {
    var check2 = address.match(/^\s*([^\s]+)(@[^\s]+)\s*$/);
    if (check2) {
      check = [check2[0], check2[1], check2[1] + check2[2], false];
    }
    else {
      check = [address, address, address, false];
    }
  }
  var fn = $.trim(check[1] || check[2].substring(0, check[2].indexOf('@')));
  if (fn.substring(0, 1) == '<') fn = fn.substring(1);
  var parsed = {
    "id": check[2],
    "fn": fn,
    "address": check[2],
    "keys": [],
    "flags": {"secure" : false, "manual": !preset}
  };
  if (check[3]) {
    parsed["keys"] = [{"fingerprint": check[3].substring(1)}];
    parsed["flags"] = {"secure" : true};
  };
  return parsed;
};


/* Composer - tokenize input field (to: cc: bcc:) */
Mailpile.Composer.Recipients.Analyze = function(addresses) {
  var existing = [];

  // Is Valid & Has Multiple
  if (addresses) {
    // We know this simple strategy works, because the backend formats the
    // address lines in a conisistent way.
    var multiple = addresses.split(/>, */);

    $.each(multiple, function(key, value) {
      if (value.indexOf('@') > -1) {
        if (value.indexOf('<') == -1) value = value + ' <' + value;
        if (value.indexOf('>') == -1) value = value + '>';
      }
      existing.push(Mailpile.Composer.Recipients.AnalyzeAddress(value, true));
    });
  }
  return existing;
};


Mailpile.Composer.Recipients.RecipientToAddress = function(object) {
  if (object.flags.secure) {
    address = object.address + '#' + object.keys[0].fingerprint;
  } else {
    address = object.address;
  }
  if (object.fn !== "" && object.address !== object.fn) {
    return object.fn + ' <' + address + '>';
  } else {
    return '<' + address + '>';
  }
};


/* Composer - instance of select2 */
Mailpile.Composer.Recipients.AddressField = function(id) {

  // Get MID
  var mid = $('#' + id).data('mid');

  $('#' + id).select2({
    id: Mailpile.Composer.Recipients.RecipientToAddress,
    ajax: {
      // instead of writing the function to execute the request we use
      // Select2's convenient helper
      url: Mailpile.api.contacts,
      quietMillis: 1,
      cache: true,
      dataType: 'json',
      data: function(term, page) {
        return {
          q: term
        };
      },
      results: function(response, page) {
        // Convert the results into the format expected by Select2
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
    createSearchChoice: Mailpile.Composer.Recipients.AnalyzeAddress,
    formatResult: function(state) {
      var avatar = '<span class="icon-user"></span>';
      var secure = '';
      if (state.photo) {
        avatar = '<img src="' + _.escape(state.photo) + '">';
      }
      if (state.flags.secure) {
        secure = '<span class="icon-lock-closed"></span>';
      }
      return ('<span class="compose-select-avatar">' + avatar + '</span>' +
              '<span class="compose-select-name">' + 
              _.escape(state.fn) + secure + '<br>' +
              '<span class="compose-select-address">' + state.address +
              '</span></span>');
    },
    formatSelection: function(state, elem) {
      // Update Model
      var found = false;
      var model = Mailpile.Composer.Drafts[mid];
      for (i in model.addresses) {
        var contact_data = model.addresses[i];
        if (contact_data.address == state.address) {
          if (state.flags.manual) {
            state.photo = contact_data.photo;
            model.addresses[i] = state;
          }
          else {
            state = model.addresses[i];
          }
          found = i;
        }
      }
      if (!found) {
        found = Math.random().toString(16).substring(6);
        model.addresses[found] = state;
      }

      // Create HTML
      var avatar = '<span class="avatar icon-user" data-address="' + _.escape(state.address) + '"></span>';
      var name   = state.fn;
      var secure = '';

      if (state.photo) {
        avatar = '<span class="avatar"><img src="' + _.escape(state.photo) + '" data-address="' + state.address + '"></span>';
      }

      if (!state.fn) {
        name = state.address;
      }

      if (state.flags.secure) {
        secure = '<span class="icon-lock-closed" data-address="' + _.escape(state.address) + '"></span>';
      }

      if (!state.fn){
      return avatar + ' <span class="compose-choice-name" data-address="' + _.escape(state.address) + '">' + _.escape(state.address) + secure + '</span>';
      } else {
      return avatar + ' <span class="compose-choice-name" data-address="' + _.escape(state.address) + '">' + _.escape(name) + secure + '</span>';
      }
    },
    formatSelectionTooBig: function() {
      return 'You\'ve added the maximum contacts allowed, to increase this go to <a href="#">settings</a>';
    },
    selectOnBlur: true

  }).on('select2-selecting', function(e) {
    setTimeout(function() {
      Mailpile.Composer.Crypto.UpdateEncryptionState(mid);
      Mailpile.Composer.Tooltips.ContactDetails();
    }, 50);
  }).on('select2-removed', function(e) {
    setTimeout(function() {
      Mailpile.Composer.Crypto.UpdateEncryptionState(mid);
    }, 50);
  });

  /* Check encryption state */
  $('#'+id).select2('data', Mailpile.Composer.Recipients.Analyze($('#' + id).val()));
};

Mailpile.Composer.Recipients.Update = function(mid, which, rcpts) {
  var $elem = $('#compose-' + which + '-' + mid);
  $elem.select2('data', rcpts);
  Mailpile.Composer.Tooltips.ContactDetails();
};
