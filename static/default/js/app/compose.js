/* Create New Blank Message */
$(document).on('click', '#button-compose', function() {
	$.ajax({
		url			 : mailpile.api.compose,
		type		 : 'POST',
		data     : {},
		dataType : 'json'  
  }).done(function(response) {
      if (response.status == 'success') {
        window.location.href = mailpile.urls.message_draft + response.result.created + '/';
      }
      else {
        statusMessage(response.status, response.message);
      }      
  });
});



/* Is Compose Page -  Probably want to abstract this differently */
if ($('#form-compose').length) {


  // Auto Select To: field


  // AJAX Load Contacts
  $.getJSON(mailpile.api.contacts, function(contacts) {


    var formatContactResult = function(state) {
      if (!state.id) return state.text;
      return "<span class='icon-user'></span> &nbsp;" + state.text;
    }          

      
    $("#compose-to, #compose-cc, #compose-bcc").select2({
      tags: contacts[0].result.contacts,          // Load contact list (items in javascrupt array [])
      multiple: true,
      allowClear: true,
      placeholder: 'name or email address',  // Placeholder
      width: '70%',                               // Width of input element
      maximumSelectionSize: 50,                   // Limits number of items added
      tokenSeparators: [",", " - "],
      formatResult: formatContactResult,
      formatSelection: formatContactResult,    
      formatSelectionTooBig: function() {
        return 'You\'ve added the maximum contacts allowed, to increase this go to <a href="#">settings</a>';
      }
    });

    $("#compose-to, #compose-cc, #compose-bcc").on("change", function() {
      $("#compose-to_val").html($("#compose-to").val());
    });

    $("#compose-to, #compose-cc, #compose-bcc").select2("container").find("ul.select2-choices").sortable({
      containment: 'parent',
      start: function() { 
        $("#compose-to, #compose-cc, #compose-bcc").select2("onSortStart");
      },
      update: function() {
        $("#compose-to, #compose-cc, #compose-bcc").select2("onSortEnd");
      }
    });
  });
}


$(document).on('click', '.compose-show-field', function(e) {
  
  $(this).hide();
  $('#compose-' + $(this).html().toLowerCase() + '-html').show();
  
});


/* Send & Save */
$(document).on('click', '.compose-action', function(e) {

  e.preventDefault();
  var action = $(this).val();

  if (action == 'send') {
	  var action_url     = mailpile.api.compose_send;
	  var action_status  = 'success';
	  var action_message = 'Your message was sent <a id="status-undo-link" data-action="undo-send" href="#">undo</a>';
  }
  else if (action == 'save') {
	  var action_url     = mailpile.api.compose_save;
	  var action_status  =  'info';
	  var action_message = 'Your message was saved';
  }

	$.ajax({
		url			 : action_url,
		type		 : 'POST',
		data     : $('#form-compose').serialize(),
		dataType : 'json',
	  success  : function(response) {

      if (action == 'send' && response.status == 'success') {
        window.location.href = mailpile.urls.message_sent + response.result.messages[0].mid
      }
      else {
        statusMessage(response.status, response.message);
      }
	  }
	});
});
