/* Compose - Perform autosave checking & save */
Mailpile.compose_autosave = function(mid, form_data) {

  // Text is different, run autosave
  if ($('#compose-text-' + mid).val() !== Mailpile.messages_composing['compose-text-' + mid]) {

    // UI Feedback
    var autosave_msg = $('#compose-message-autosaving-' + mid).data('autosave_msg');
    $('#compose-message-autosaving-' + mid).html(autosave_msg).fadeIn();

    // 
  	$.ajax({
  		url			 : Mailpile.api.compose_save,
  		type		 : 'POST',
      timeout  : 15000,
  		data     : form_data,
  		dataType : 'json',
  	  success  : function(response) {

        // Update Message (data model)
        Mailpile.messages_composing[mid] = $('#compose-text-' + mid).val();

        // Fadeout autosave UI msg
        setTimeout(function() {
          $('#compose-message-autosaving-' + mid).fadeOut();
        }, 2000);
      },
      error: function() {
        var autosave_error_msg = $('#compose-message-autosaving-' + mid).data('autosave_error_msg');
        $('#compose-message-autosaving-' + mid).html('<span class="icon-x"></span>' + autosave_error_msg).fadeIn();
      }
  	});
  }
};


/* Compose Autosave - finds each compose form and performs action */
Mailpile.compose_autosave_timer = $.timer(function() {
  // UNTESTED: should handle multiples in a thread
  $('.form-compose').each(function(key, form) {
    Mailpile.compose_autosave($(form).data('mid'), $(form).serialize());
  });
});
