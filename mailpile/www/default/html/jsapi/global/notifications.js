/* Notifications - UI notification at top of window */

Mailpile.cancel_notification = function(not_id, $existing) {
  // Cancel existing notification, if any
  var $existing = $existing || $('#event-' + not_id);
  if ($existing.length > 0) {
    clearTimeout($existing.data('timeout_id'));
    $existing.remove();
  }
};


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
  if (result.action === undefined) {
    if (result.flags == "c") {
      result.action = 8000; // Event complete, timeout quickly
    }
    else {
      result.action = 360000000; // 100 hours - awaite completion
    }
  }
  if (result.icon === undefined) {
    result.icon = 'icon-inbox';
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
    result.action = 20000;
  }

  // Show Notification
  Mailpile.cancel_notification(result.event_id);
  var notification_template = _.template($('#template-notification-bubble').html());
  $('#notification-bubbles').prepend(notification_template(result));
  setTimeout(function() {
    $('#event-' + result.event_id).fadeIn('fast');
  }, 250);

  // If Not Nagify, default
  if (result.complete === 'hide' && result.type !== 'nagify') {
    var to_id = setTimeout(function() {
      $('#event-' + result.event_id).fadeOut('normal', function() {
        $(this).remove();
      });
    }, result.action);
    $('#event-' + result.event_id).data('timeout_id', to_id);
  }
  else if (result.complete == 'redirect') {
    setTimeout(function() {
      window.location.href = result.action 
    }, 4000);
  }
};


/* Notification - Close */
$(document).on('click', '.notification-close', function() {
  if ($(this).data('type') === 'nagify') {
    var next_nag = new Date().getTime() + Mailpile.nagify;
    Mailpile.API.settings_set_post({ 'web.nag_backup_key': next_nag });
  }
  Mailpile.cancel_notification('', $(this).parent());
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


/* Notification - Nag */
$(document).on('click', '.notification-nag', function(e) {
  e.preventDefault();
  var href = $(this).attr('href');
  var next_nag = new Date().getTime() + Mailpile.nagify;
  Mailpile.API.settings_set_post({ 'web.nag_backup_key': next_nag }, function() {
    window.location.href = href;
  });
});


/* Connection Down - Hide */
$(document).on('click', '#connection-down-hide', function() {
  $('#connection-down').fadeOut().remove();
});


/* Set up some default notifications by listening to the Event log */
EventLog.subscribe('.*AddProfile', function(ev) {
  console.log('AddProfile event: ' + ev.data.keygen_started);
  if (ev.data.keygen_started > 0) {
      ev.icon = 'icon-lock-closed';
      var $icon = $('.profile-' + ev.data.profile_id + '-key.icon');
      if (ev.data.keygen_finished > 0) {
          $icon.removeClass('unconfigured');
          $icon.removeClass('icon-clock').removeClass('icon-lock-open');
          $icon.addClass('configured').addClass('icon-lock-closed');
      }
      else {
          $icon.removeClass('configured').removeClass('icon-lock-closed');
          $icon.addClass('unconfigured').addClass('icon-clock');
      }
      Mailpile.notification(ev);
  }
});
EventLog.subscribe('.*mail_source.*', function(ev) {
  var $src = $('.source-' + ev.data.id);
  if ($src.length > 0) {
    ev.icon = 'icon-mailsource';
    Mailpile.notification(ev);

    var $icon = $src.find('.icon');
    if (ev.data.connection.error[0]) {
      $icon.removeClass('configured').removeClass('unconfigured');
      $icon.addClass('misconfigured');
      $src.attr('title', $src.data('title') + '\n\n' +
                         '{{_("Error")}}: ' +  ev.message);
    }
    else {
      $icon.removeClass('misconfigured').removeClass('unconfigured');
      $icon.addClass('configured');
    }
  }
});
