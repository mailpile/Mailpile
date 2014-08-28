/* Notifications - UI notification at top of window */
Mailpile.notification = function(result, complete, complete_action) {

  if (result.event_id !== undefined) {
    result.event_id = result.event_id.split('.').join('-');
  } else {
    result['event_id'] = 'fake-id-'+Math.random().toString(24).substring(2);
  }

  var default_messages = {
    "success" : "Success, we did what you asked",
    "info"    : "Here is a basic info update",
    "debug"   : "This is a simple debug message",
    "warning" : "This here be a warning to you",
    "error"   : "You have discovered an error"
  }

  if (result.message == undefined) {
    result.message = default_messages[result.status];
  }

  if (result.undo == undefined) {
    result['undo'] = false;
  }

  var notification_data = _.extend(result, {
    icon: 'icon-message'
  });

  // Add Notification
  var notification_html = _.template($('#template-notification-bubble').html(), notification_data);
  $('#notification-bubbles').append(notification_html);
  setTimeout(function() {
    $('#event-' + result.event_id).fadeIn('fast');
  }, 250);
  

  // Complete Action
  if (complete == undefined) {
    setTimeout(function() {
      $('#event-' + result.event_id).fadeOut(function() {
        $(this).remove();
      });
    }, 8000);
  } else if (complete == 'hide') {
      message.delay(5000).fadeOut('normal', function() {
          message.find('span.message-text').empty();
      });
  } else if (complete == 'redirect') {
      setTimeout(function() {
        window.location.href = complete_action 
      }, 5000);
  }

  return function() { message.fadeOut('normal'); };
};


/* Message Close */
$(document).on('click', '.notification-close', function() {
  $(this).parent().fadeOut(function() {
    $(this).remove();
  });
});


/* Connection Down - Hide */
$(document).on('click', '#connection-down-hide', function() {
  $('#connection-down').fadeOut().remove();
});