/* Compose - Autosave */

Mailpile.Composer.Autosave = function(mid, form_data, callback) {

  if (Mailpile.Composer.Drafts[mid] === undefined) {
    Mailpile.Composer.Drafts[mid] = Mailpile.Composer.Model({}, {});
    Mailpile.Composer.Body.Setup(mid);
  }

  // Has text changed, or is new?  If so, run autosave.
  if ($('#compose-text-' + mid).val() != Mailpile.Composer.Drafts[mid].body) {

    // UI Feedback
    var autosave_msg = $('#compose-message-autosaving-' + mid).data('autosave_msg');
    $('#compose-message-autosaving-' + mid).html(autosave_msg).fadeIn();

    // Autosave It
  	$.ajax({
  		url			 : Mailpile.api.compose_save,
  		type		 : 'POST',
      timeout  : 15000,
  		data     : form_data,
  		dataType : 'json',
  	  success  : function(response) {

        // Update Message (data model)
        Mailpile.Composer.Drafts[mid].body = $('#compose-text-' + mid).val();

        // Fadeout autosave UI msg
        setTimeout(function() {
          $('#compose-message-autosaving-' + mid).fadeOut();
        }, 2000);
        callback();
      },
      error: function() {
        var autosave_error_msg = $('#compose-message-autosaving-' + mid).data('autosave_error_msg');
        $('#compose-message-autosaving-' + mid).html('<span class="icon-x"></span>' + autosave_error_msg).fadeIn();
        callback();
      }
  	});

  }
  // Not Autosaving
  else {
    callback();
  }
};


Mailpile.Composer.AutosaveAll = function(delay, callback) {
  var save_chain = [];
  $('.form-compose').each(function(key, form) {
    save_chain.push(function(chain) {
      Mailpile.Composer.Autosave($(form).data('mid'), $(form).serialize(),
                                 function() {
        if (chain && chain.length) {
          var nxt = chain.shift();
          if (delay) {
            setTimeout(function() { nxt(chain); }, delay)
          }
          else {
            nxt(chain);
          }
        }
      });
    });
  });
  if (callback) save_chain.push(callback);
  if (save_chain.length) save_chain.shift()(save_chain);
}


/* Compose Autosave - finds each compose form and performs action */
Mailpile.Composer.AutosaveTimer = $.timer(function() {
  Mailpile.Composer.AutosaveAll(250);
});
