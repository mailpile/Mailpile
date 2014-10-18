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
  Mailpile.Composer.Crypto.load_states();

  // Instantiate select2
  Mailpile.Composer.Recipients.address_field('compose-to-' + mid);

  // Save Text Composing Objects (move to data model)
  Mailpile.messages_composing['compose-text-' + mid] = $('#compose-text-' + mid).val();


  // Initialize Attachments
  // FIXME: needs to be bound to unique ID that can be destroyed
  Mailpile.Composer.Attachments.uploader({
    browse_button: 'compose-attachment-pick-' + mid,
    container: 'compose-attachments-' + mid,
    mid: mid
  });

  // Show Crypto Tooltips
  Mailpile.Composer.Tooltips.signature();
  Mailpile.Composer.Tooltips.encryption();
  Mailpile.Composer.Tooltips.contact_details();

  // Autosize
  //$('#compose-text-' + mid).autosize();

};