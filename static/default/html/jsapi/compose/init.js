/* Compose - Create new instance of composer */
Mailpile.compose_init = function(mid) {

  // Reset tabindex for To: field
  $('#search-query').attr('tabindex', '-1');

  // Load Crypto States
  // FIXME: needs dynamic support for multi composers on a page
  Mailpile.compose_load_crypto_states();

  // Instantiate select2
  Mailpile.compose_address_field('compose-to-' + mid);
  // FIXME: move to click events
  Mailpile.compose_address_field('compose-cc-' + mid);
  Mailpile.compose_address_field('compose-bcc-' + mid);


  // Save Text Composing Objects (move to data model)
  Mailpile.messages_composing['compose-text-' + mid] = $('compose-text-' + mid).val();


  // Run Autosave
  // FIXME: this should be moved to the global event loop
  Mailpile.compose_autosave_timer.play();
  Mailpile.compose_autosave_timer.set({ time : 20000, autostart : true });


  // Initialize Attachments
  // FIXME: needs to be bound to unique ID that can be destroyed
  uploader({
    browse_button: 'compose-attachment-pick-' + mid,
    container: 'compose-attachments-' + mid,
    mid: mid
  });


  // Show Crypto Tooltips
  Mailpile.tooltip_compose_crypto_signature();
  Mailpile.tooltip_compose_crypto_encryption();
  Mailpile.tooltip_compose_contact_details();

};