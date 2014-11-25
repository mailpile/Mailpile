/* Modals - Crypto */

/* Modals - Crypto - try to find keys locally & remotely */
Mailpile.UI.Modals.CryptoFindKeys = function(options) {

  // Set Defaults
  options.container = '#search-keyservers';
  options.action    = 'hide-modal';
  options.complete  =  function() {
    $('#search-keyservers').find('.loading').slideUp('fast');
  };

  // Async call
  Mailpile.API.async_crypto_keylookup_get({"address": options.query }, function(data, ev) {

    // Render each result found
    if (data.result) {
    
      $(options.container).find('.message')
        .html('<span class="icon-key"></span> ' + data.message)
        .removeClass('paragraph-important paragraph-alert')
        .addClass('paragraph-success');
      Mailpile.Crypto.Find.KeysResult(data, options);
    }

    // Running Search
    if (data.runningsearch) {
      var searching_template = _.template($("#template-find-keys-running").html());
      var searching_html = searching_template(options);
      $(options.container).find('.message')
        .html(searching_html)
        .removeClass('paragraph-alert paragraph-success')
        .addClass('paragraph-important');
    }
    else {
      Mailpile.Crypto.Find.KeysDone(options);
    }
  });

  // Show Modal
  var modal_template = _.template($('#modal-search-keyservers').html());
  $('#modal-full').html(modal_template(options));
  $('#modal-full').modal(Mailpile.UI.ModalOptions);
};

