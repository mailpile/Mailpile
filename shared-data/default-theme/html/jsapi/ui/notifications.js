/* Notifications - UI notification at top of window */

Mailpile.expire_canceled_notifictions = function() {
  var expired = new Date().getTime() - (3600 * 1000);
  for (item in Mailpile.local_storage) {
    if (item.indexOf('canceled-') == '0'
        && Mailpile.local_storage[item] < expired) {
      delete Mailpile.local_storage[item];
    }
  }
};
Mailpile.expire_canceled_notifictions();


Mailpile.cancel_notification = function(not_id, $existing, replace, record) {
  // Cancel existing notification, if any
  var $existing = $existing || $('#event-' + not_id);
  if ($existing.length > 0) {
    clearTimeout($existing.data('timeout_id'));
    if (replace) {
      return $existing;
    }
    else {
      if (record) {
        not_id = $existing.attr('id').substring(6);
        Mailpile.local_storage['canceled-' + not_id] = new Date().getTime();
      }
      $existing.slideUp('normal', function() {
        $(this).remove();
        if ($('.notification-bubble').length < 1) {
          $('.notifications-close-all span').hide();
        }
      });
    }
  }
  return undefined;
};


Mailpile.notification = function(result) {

  // Create CSS friend event_id OR fake-id
  if (result.event_id !== undefined) {
    result.event_id = result.event_id.split('.').join('-');
  } else {
    result.event_id = 'fake-id-' + Math.random().toString(24).substring(2);
  }

  // Message
  var default_messages = {
    "success" : "Success, we did what you asked",
    "info"    : "Here is a basic info update",
    "debug"   : "This is a simple debug message",
    "warning" : "This here be a warning to you",
    "error"   : "You have discovered an error"
  }
  if (result.message  === undefined) {
    result.message = default_messages[result.status];
  }

  // Default Options
  if (result.message2 === undefined) {
    if (result.data && result.data.name) {
      result.message2 = result.message;
      result.message = result.data.name;
    }
    else {
      result.message2 = '';
    }
  }
  if (result.undo        === undefined) result.undo = false;
  if (result.type        === undefined) result.type = 'notify';
  if (result.complete    === undefined) result.complete = 'hide';
  if (result.action      === undefined) result.action = '';
  if (result.action_js   === undefined) result.action_js = '';
  if (result.action_url  === undefined) result.action_url = '';
  if (result.action_text === undefined) result.action_text = '';
  if (result.icon        === undefined) result.icon = 'icon-inbox';
  if (result.timeout     === undefined) {
    if (result.flags == "c") {
      result.timeout = 8000; // Event complete, timeout quickly
    }
    else {
      result.timeout = 360000000; // 100 hours - awaite completion
    }
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
    result.timeout = 20000;
  }

  // If user has canceled this notification, don't bug him again.
  if (Mailpile.local_storage['canceled-' + result.event_id]) {
    return result.event_id;
  }

  // Show Notification
  var $elem = Mailpile.cancel_notification(result.event_id, undefined, 'keep');
  var notification_template = Mailpile.unsafe_template($('#template-notification-bubble').html());
  if ($elem) {
      $elem.replaceWith(notification_template(result));
  }
  else {
      var bubbles = $('#notification-bubbles');
      if (bubbles.children().length < 15) {
          bubbles.prepend($(notification_template(result)).slideDown('normal'));
          $('.notifications-close-all span').show();
      }
  }

  // If Not Nagify, default
  if (result.complete === 'hide' && result.type !== 'nagify') {
    var to_id = setTimeout(function() {
      Mailpile.cancel_notification(result.event_id);
    }, result.timeout);
    $('#event-' + result.event_id).data('timeout_id', to_id);
  }
  else if (result.complete == 'redirect') {
    setTimeout(function() {
      Mailpile.go(result.action);
    }, 4000);
  }

  return result['event_id'];
};

/* Use when stuff is loading in the backgrount to show progress */
Mailpile.notify_working = function(message, timeout) {
  var events = [undefined, undefined];
  var notify = function() {
    var silly = Math.floor(Math.random() * Mailpile.silly_strings.misc.length);
    events[1] = Mailpile.notification({
      event_id: events[1],
      message: message || "{{_('Working...')|escapejs}}",
      message2: Mailpile.silly_strings.misc[silly],
      status: 'warning',
      icon: 'icon-robot'
    });
    events[0] = setTimeout(notify, 5000);
  };
  events[0] = setTimeout(notify, timeout);
  return function() {
    // This cancels the event. To avoid weird flickering, if the notification
    // has already been displayed, we leave it up for a little longer.
    if (events[0]) clearTimeout(events[0]);
    setTimeout(function() {
      if (events[1]) Mailpile.cancel_notification(events[1]);
    }, 1250);
  }
};

/* Notification - Close all */
$(document).on('click', '.notifications-close-all', function() {
  $('.notification-close').click();
});



/* Notification - Close */
$(document).on('click', '.notification-close', function() {
  if ($(this).data('type') === 'nagify') {
    var next_nag = new Date().getTime() + Mailpile.nagify;
    Mailpile.API.settings_set_post({ 'web.nag_backup_key': next_nag });
  }
  Mailpile.cancel_notification('', $(this).parent(), undefined, true);
});


/* Notification - Undo */
$(document).on('click', '.notification-undo', function() {
  var event_id = $(this).data('event_id').split('.').join('-');
  Mailpile.API.logs_events_undo_post({ event_id: event_id }, function(result) {
    if (result.status === 'success') {
      window.location.reload(true);
    }
    else {
      alert("{{ _('Oops. Mailpile failed to complete your task.') }}");
    }
  });
});


/* Notification - Nag */
$(document).on('click', '.notification-nag', function(e) {
  e.preventDefault();
  var href = $(this).attr('href');
  var next_nag = new Date().getTime() + Mailpile.nagify;
  Mailpile.API.settings_set_post({ 'web.nag_backup_key': next_nag }, function() {
    Mailpile.go(href);
  });
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
          $icon.removeClass('configured');
          $icon.removeClass('icon-lock-open').removeClass('icon-lock-closed');
          $icon.addClass('unconfigured').addClass('icon-clock');
      }
      Mailpile.notification(ev);
  }
});
EventLog.subscribe('.*mail_source.*', function(ev) {
  var $src = $('.source-' + ev.data.id);
  if ($src.length > 0) {
    var $icon = $src.find('.icon');
    if (ev.data.connection && ev.data.connection.error[0]) {
      $icon.removeClass('configured').removeClass('unconfigured');
      $icon.addClass('misconfigured');
      $src.attr('title', $src.data('title') + '\n\n' +
                         '{{_("Error")|escapejs}}: ' +  ev.message);
      ev.action_js = "onclick=\"javascript:$('.source-" + ev.data.id + "').click();\"";
      ev.action_text = '{{_("edit settings")|escapejs}}';
    }
    else {
      $icon.removeClass('misconfigured').removeClass('unconfigured');
      $icon.addClass('configured');
    }

    ev.icon = 'icon-mailsource';
    Mailpile.notification(ev);
  }
});
EventLog.subscribe('.*compose.Sendit', function(ev) {
  if (ev.data.delivered == ev.data.recipients) {
    ev.icon = 'icon-outbox';
  }
  else if (ev.data.last_error) {
    ev.icon = 'icon-signature-unknown';
    ev.message2 = ev.data.last_error
  }
  Mailpile.notification(ev);
});
