/* Composer */
Mailpile.Composer = {};
Mailpile.Composer.Crypto = {};
Mailpile.Composer.Recipients = {};
Mailpile.Composer.Tooltips = {};
Mailpile.Composer.Attachments = {};

/* Composer - Create new instance of composer */
Mailpile.Composer.init = function(mid) {

  // Reset tabindex for To: field
  $('#search-query').attr('tabindex', '-1');

  // Load Crypto States
  // FIXME: needs dynamic support for multi composers on a page
  Mailpile.Composer.Crypto.LoadStates(mid);

  // Instantiate select2
  Mailpile.Composer.Recipients.AddressField('compose-to-' + mid);

  // Save Text Composing Objects (move to data model)
  Mailpile.messages_composing['compose-text-' + mid] = $('#compose-text-' + mid).val();


  // Initialize Attachments
  // FIXME: needs to be bound to unique ID that can be destroyed
  Mailpile.Composer.Attachments.Uploader({
    browse_button: 'compose-attachment-pick-' + mid,
    container: 'compose-attachments-' + mid,
    mid: mid
  });

  // Show Crypto Tooltips
  Mailpile.Composer.Tooltips.Signature();
  Mailpile.Composer.Tooltips.Encryption();
  Mailpile.Composer.Tooltips.ContactDetails();

  // Autosize
  //$('#compose-text-' + mid).autosize();

};