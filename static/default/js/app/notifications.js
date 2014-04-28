MailPile.prototype.notification = function(status, message_text, complete, complete_action) {

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
  message.fadeIn();

	// Complete Action
	if (complete == undefined) {
    
  }
	else if (complete == 'hide') {
		message.delay(5000).fadeOut('normal', function() {
			message.find('span.message-text').empty();
		});
	}
	else if (complete == 'redirect') {
		setTimeout(function() { window.location.href = complete_action }, 5000);
	}

  return false;
}


/* Event Log - AJAX Polling */
MailPile.prototype.poll_event_log =  $.timer(function() {

	console.log('eventlog ------------------------------------- polled');

  // Check Global State
//  if (NewOverviewToolsModel.get('state') === "complete") {
		// Stop the whole Shabang!
		this.stop();
//  }
//  else {
  	$.ajax({
  		url: '/api/0/eventlog/', //?=' + new Date().getTime(),
  		type: 'GET',
  		dataType: 'json',
  		cache: 'false',
  		timeout: 3500,
      success: function(result) {
  			// Process Result
//  		NewOverviewToolsModel.processTool(tool, result);
      }
  	});

//  }

});


$(document).on('click', '.topbar-logo, .topbar-logo-name', function(e) {

  e.preventDefault();
  $('#notifications').show();

  // Hide Notifications
  $('body').click(function () {  
    $('#notifications').hide();
  });
});



$(document).ready(function() {

  /* Message Close */
	$('.message-close').on('click', function() {
		$(this).parent().fadeOut(function() {
			//$('#header').css('padding-top', statusHeaderPadding());
		});
	});

  // Kick the whole Shabang off
  mailpile.poll_event_log.play();
  mailpile.poll_event_log.set({ time : 5000, autostart : true });

});