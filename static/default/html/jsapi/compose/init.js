/* Compose - DOM ready */
Mailpile.compose_init = function(mid) {

  console.log('running init for composer');
  
  // Reset tabindex for To: field
  $('#search-query').attr('tabindex', '-1');

  // Load Crypto States
  // FIXME: needs dynamic support for multi composers on a page
  Mailpile.compose_load_crypto_states();

  // Instantiate select2
  $('.compose-address-field').each(function(key, elem) {
    Mailpile.compose_address_field($(elem).attr('id'));
  });

  // Save Text Composing Objects
  $('.compose-text').each(function(key, elem) {
      Mailpile.messages_composing[$(elem).attr('id')] = $(elem).val()
  });

  // Run Autosave
  Mailpile.compose_autosave_timer.play();
  Mailpile.compose_autosave_timer.set({ time : 20000, autostart : true });

  // Initialize Attachments
  // FIXME: needs dynamic support for multi composers on a page
  $('.compose-attachments').each(function(key, elem) {
    var mid = $(elem).data('mid');
    console.log('js uploader: ' + mid);
    uploader({
      browse_button: 'compose-attachment-pick-' + mid,
      container: 'compose-attachments-' + mid,
      mid: mid
    });
  });

  // Show Crypto Tooltips
  Mailpile.tooltip_compose_crypto_signature();
  Mailpile.tooltip_compose_crypto_encryption();
  Mailpile.tooltip_compose_contact_details();

};