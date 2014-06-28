/* Crypto - Try to find keys locally & remotely */
Mailpile.find_missing_keys = function(address) {

  $("#modal-full").html($("#modal-search-keyservers").html());

  // This used to be called Mailpile.API.async_crypto_keylookup() but was undefined method
  // Also had the arg "allowremote": true which seemed to be trigger a bad variable error
  Mailpile.API.async_crypto_gpg_searchkey({"address": address}, function(data, ev) {

    if (data.result) {
      $("#modal-search-keyservers-results").html("Found " + data.result.length + " keys");
    }

    if (data.runningsearch) {
      $("#modal-search-keyservers-looking").html("Searching " + data.runningsearch + "...");
    } else {
      $("#modal-search-keyservers-looking").html();
    }

    if (ev.flags == "c") {
      $("#modal-search-keyservers-progress").html("");
    }

    $("#keyservers-result-list").html("");
    for (k in data.result) {
      var key = data.result[k];
      $("#keyserver-result-list").append("<tr>"
           + "<td>" + key.uids[0].name + " &lt;" + key.uids[0].email + "&gt;</td>"
           + "<td>" + key.fingerprint.split(/(....)/).join(" ") + "</td>"
           + "<td><input type='checkbox' name='crypto-key'></td>"
           + "</tr>");
    }
  });

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

  Mailpile.API.async_crypto_gpg_receivekey({}, function() {
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

  // Update Querying UI Feedback
  $(this).hide();
  $('#contact-search-keyserver-query').hide();
  $('#contact-search-keyserver-input label').html($(this).data('searching'));
  $('#contact-search-keyserver-result').html('<img src="/static/css/select2-spinner.gif">');

  var search_complete = $(this).data('complete');
  var search_query = $(this).data('query');

  $.ajax({
    url      : '/api/0/crypto/gpg/searchkey/?q=' + search_query,
    type     : 'GET',
    dataType : 'json',
    success  : function(response) {
      if (response.status === 'success' && _.isEmpty(response.result) === false) {

        // Update Title
        $('#contact-search-keyserver-input label').html(_.size(response.result) + ' ' + search_complete + ' ' + search_query);

        // Build Results
        var items = '';
        var item_html = $('#template-search-keyserver-item').html();

        $.each(response.result, function(keyid, object) {
          $.each(object.uids, function(key, value) {
            items += _.template(item_html, { 
              keyid: keyid,
              keysize: object.keysize,
              keytype: object.keytype,
              created: object.created,
              name: value.name, 
              email: value.email
            });
          });
        });

        // Display Results
        $('#contact-search-keyserver-result').html('<ul>' + items + '</ul>');
      }
      else if (response.status === 'success' && _.isEmpty(response.result) === true) {
        $('#contact-search-keyserver-input label').html('<p>No keys found</p>');
      }
    }
  });
});