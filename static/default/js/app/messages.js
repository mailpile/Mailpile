var statusHeaderPadding = function() {

	if ($('#header').css('position') === 'fixed') {
		var padding = $('#header').height() + 50;
	}
	else {
		var padding = 0;
	}

	return padding;
};



var statusMessage = function(status, message_text, complete, complete_action) {

  var default_messages = {
    "success" : "Success, we did exactly what you asked.",
    "info"    : "Here is a basic info update",
    "debug"   : "What kind of bug is this bug, it's a debug",
    "warning" : "This here be a warnin to you, just a warnin mind you",
    "error"   : "Whoa cowboy, you've mozyed on over to an error"
  }

  var message = $('#messages').find('div.' + status);

  if (message_text == undefined) {
    message_text = default_messages[status];
  }

  // Show Message
  message.find('span.message-text').html(message_text),
  message.fadeIn(function() {

    // Set Padding Top for #content
	  // $('#header').css('padding-top', statusHeaderPadding());
  });

	// Complete Action
	if (complete == undefined) {

  }
	else if (complete == 'hide') {
		message.delay(5000).fadeOut('normal', function()
		{
			message.find('span.message-text').empty();
		});
	}
	else if (options.complete == 'redirect') {
		setTimeout(function() { window.location.href = complete_action }, 5000);
	}

  return false;
}


$(document).ready(function() {


  /* Message Close */
	$('.message-close').on('click', function() {
		$(this).parent().fadeOut(function() {
			//$('#header').css('padding-top', statusHeaderPadding());
		});
	});

});