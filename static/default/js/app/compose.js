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

  var formatComposeId = function(object) {
    if (object.address != object.fn) {
      return object.fn + ' <' + object.address + '>';
    } else {
      return object.address;
    }
  }

  var formatComposeResult = function(state) {
    var keys = '';
    if (state.keys != undefined) {
      keys = '<span class="icon-verified"></span>';
    }    
    return '<span class="icon-user"></span><span class="compose-select-name">' + state.fn + keys + '</span><span class="compose-select-address">' + state.address + '</span>';
  }

  var formatComposeSelection = function(state) {
    var keys = '';
    if (state.keys != undefined) {
      keys = '<span class="icon-verified"></span>';
    }
    return '<span class="icon-user"></span> ' + state.fn + keys;
  }


  $("#compose-to, #compose-cc, #compose-bcc").select2({
    id: formatComposeId,  
    ajax: { // instead of writing the function to execute the request we use Select2's convenient helper
      url: mailpile.api.contacts,
      quietMillis: 1,
      cache: true,
      dataType: 'json',
      data: function(term, page) {
        return {
          q: term
          //count: 120,
          //offset: 0
        };
      },
      results: function(response, page) {         
        // parse the results into the format expected by Select2.
        // since we are using custom formatting functions we do not need to alter remote JSON data
        return {
          results: response.result.addresses
        };
      }
    },
    tags: [""],          // Load contact list (items in javascrupt array [])
    multiple: true,
    allowClear: true,
    width: '425',                               // Width of input element
    maximumSelectionSize: 50,                   // Limits number of items added
    tokenSeparators: [","],
    createSearchChoice: function(term) {
      console.log('Inside of createSearchChoice');
      console.log(term);
      // Need to validate
      term.fn = term;
      return term;
    },
    formatResult: formatComposeResult,
    formatSelection: formatComposeSelection,    
    formatSelectionTooBig: function() {
      return 'You\'ve added the maximum contacts allowed, to increase this go to <a href="#">settings</a>';
    },
    selectOnBlur: true,
    opening: function() {
      console.log('there times they are a changing');
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


}


$(document).on('click', '.compose-show-field', function(e) {
  
  $(this).hide();
  $('#compose-' + $(this).html().toLowerCase() + '-html').show();
  
});


/* Subject Field */
$(window).keyup(function (e) {
  var code = (e.keyCode ? e.keyCode : e.which);
  if (code == 9 && $('#compose-subject:focus').length) {
  }
});

$(window).on('click', '#compose-subject', function() {
  this.focus();
  this.select();
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
