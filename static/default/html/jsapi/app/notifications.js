/* Notifications - UI notification at top of window */
Mailpile.notification = function(result) {

  // Create CSS friend event_id OR fake-id
  if (result.event_id !== undefined) {
    result.event_id = result.event_id.split('.').join('-');
  } else {
    result['event_id'] = 'fake-id-' + Math.random().toString(24).substring(2);
  }

  // Message
  var default_messages = {
    "success" : "Success, we did what you asked",
    "info"    : "Here is a basic info update",
    "debug"   : "This is a simple debug message",
    "warning" : "This here be a warning to you",
    "error"   : "You have discovered an error"
  }

  if (result.message === undefined) {
    result['message'] = default_messages[result.status];
  }

  // Default Options
  if (result.undo === undefined) {
    result.undo = false;
  }
  if (result.type === undefined) {
    result.type = 'notify';
  }
  if (result.complete === undefined) {
    result.complete = 'hide';
  }
  if (result.complete_action === undefined) {
    result.complete_action = 8000
  }
  if (result.icon === undefined) {
    result.icon = 'icon-message';
  }

  // Undo & Icon
  if (result.command !== 'tag' && result.type === 'nagify') {
    result.undo = false;
    result.icon = 'icon-signature-unknown';
  }
  else if (result.command === 'tag') {
    result.undo = true;
    result.icon = 'icon-tag';
  }

  // If Undo, extend hide
  if (result.undo && result.complete === 'hide') {
    result.complete_action = 20000;
  }


  // Show Notification
  var notification_html = _.template($('#template-notification-bubble').html(), result);
  $('#notification-bubbles').append(notification_html);
  setTimeout(function() {
    $('#event-' + result.event_id).fadeIn('fast');
  }, 250);


  // If Not Nagify, default
  if (result.complete === 'hide' && result.type !== 'nagify') {
    setTimeout(function() {
      $('#event-' + result.event_id).fadeOut('normal', function() {
        $(this).remove();
      });
    }, result.complete_action);
  }
  else if (result.complete == 'redirect') {
    setTimeout(function() {
      window.location.href = result.complete_action 
    }, 4000);
  }
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