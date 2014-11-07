/* Modals - Crypto */

/* Modals - Crypto - try to find keys locally & remotely */
Mailpile.UI.Modals.CryptoFindKeys = function(options) {


  Mailpile.API.async_crypto_keylookup_get({"address": options.query }, function(data, ev) {

    // Render each result found
    if (data.result) {
      $('#search-keyservers-message')
        .html('<span class="icon-checkmark"></span> ' + data.message)
        .removeClass('paragraph-important paragraph-alert')
        .addClass('paragraph-success');
      Mailpile.Crypto.Find.KeysResult(data, options);
    }

    // Running Search
    if (data.runningsearch) {
      var searching_template = _.template($("#template-searchkey-running").html());
      var searching_html = searching_template({ query: options.query });
      $(options.message)
        .html(searching_html)
        .removeClass('paragraph-alert paragraph-success')
        .addClass('paragraph-important');
    }
    else {
      Mailpile.Crypto.Find.KeysDone(options);
    }
  });

  // Show Modal
  $('#modal-full').html($('#modal-search-keyservers').html());
  $('#modal-full').modal(Mailpile.UI.ModalOptions);
};

