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

  if (result.command === 'tag') {
    result['undo'] = true;
    var hide_notification = 20000;
  }
  else {
    result['undo'] = false;
    var hide_notification = 8000;
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
    }, hide_notification);
  } else if (complete == 'hide') {
      message.delay(5000).fadeOut('normal', function() {
          message.find('span.message-text').empty();
      });
  } else if (complete == 'redirect') {
      setTimeout(function() {
        window.location.href = complete_action 
      }, 4000);
  }

  return function() { message.fadeOut('normal'); };
};


/* Notification - Close */
$(document).on('click', '.notification-close', function() {
  $(this).parent().fadeOut(function() {
    $(this).remove();
  });
});


/* Notification - Undo */
$(document).on('click', '.notification-undo', function() {
  var event_id = $(this).data('event_id').split('-').join('.');
  Mailpile.API.eventlog_undo_post({ event_id: event_id }, function(result) {
    if (result.status === 'success') {
      window.location.reload(true);
    }
  });
});


/* Connection Down - Hide */
$(document).on('click', '#connection-down-hide', function() {
  $('#connection-down').fadeOut().remove();
});