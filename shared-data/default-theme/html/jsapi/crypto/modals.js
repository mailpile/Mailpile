/* Modals - Crypto */

/* Modals - Crypto - try to find keys locally & remotely */
Mailpile.UI.Modals.CryptoFindKeys = function(options) {
  options.container = '#search-keyservers';
  options.action = 'hide-modal';
  options.searched = function() {
    $('#search-keyservers').find('.loading').slideUp('fast');
  };

  Mailpile.API.with_template('modal-search-keyservers', function(modal) {
    Mailpile.UI.show_modal(modal(options));
    if (options.query) {
      Mailpile.Crypto.Find.Keys(options);
    } else {
      $('#form-search-keyservers').removeClass('hide').addClass('fadeIn');
      $('#form-search-keyservers').find('input[name=query]').focus();
    }
  });
};

Mailpile.UI.Modals.CryptoUploadKey = function(options) {
  Mailpile.API.with_template('modal-upload-key', function(modal) {
    Mailpile.UI.show_modal(modal(options));
    Mailpile.Crypto.Import.Uploader();
  });
};
