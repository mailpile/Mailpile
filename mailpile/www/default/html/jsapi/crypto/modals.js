/* Modals - Crypto */

/* Modals - Crypto - try to find keys locally & remotely */
Mailpile.UI.Modals.CryptoFindKeys = function(options) {

  // Set Defaults
  options.container = '#search-keyservers';
  options.action    = 'hide-modal';
  options.complete  =  function() {
    $('#search-keyservers').find('.loading').slideUp('fast');
  };

  // Show Modal
  var modal_template = _.template($('#modal-search-keyservers').html());
  $('#modal-full').html(modal_template(options));
  $('#modal-full').modal(Mailpile.UI.ModalOptions);

  // Run Query
  if (options.query) {
    Mailpile.Crypto.Find.Keys(options);
  } else {
    $('#form-search-keyservers').removeClass('hide').addClass('fadeIn');
    $('#form-search-keyservers').find('input[name=query]').focus();
  }
};

Mailpile.UI.Modals.CryptoUploadKey = function(options) {
  var modal_template = _.template($('#modal-upload-key').html());
  $('#modal-full').html(modal_template(options));
  $('#modal-full').modal(Mailpile.UI.ModalOptions);

  // Uploader
  Mailpile.Crypto.Import.Uploader();
};
