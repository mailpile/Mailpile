/* Notifications - UI notification at top of window */

Mailpile.expire_canceled_notifictions = function() {
  var expired = new Date().getTime() - (3600 * 1000 * 16);
  for (item in Mailpile.local_storage) {
    if (item.indexOf('canceled-') == '0'
        && Mailpile.local_storage[item] < expired) {
      delete Mailpile.local_storage[item];
    }
  }
};

Mailpile.uncancel_notification = function(not_id) {
  delete Mailpile.local_storage['canceled-' + not_id];
};

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

Mailpile.raise_mail_source_mailbox_limit = function(not_id, src_id, howhigh) {
  var settings = {};
  settings['sources.' + src_id + '.discovery.max_mailboxes'] = howhigh;
  Mailpile.API.settings_set_post(settings, function(result) {
    Mailpile.cancel_notification(not_id);
  });
};

Mailpile.certificate_error_details = function(server, event_id) {
  var url = Mailpile.API.U(
    '/crypto/tls/getcert/?host=' + server + '&ui_tls_failed=True');
  Mailpile.auto_modal({ url: url, method: 'POST', sticky: true });
  //Mailpile.cancel_notification(event_id);
};

Mailpile.profile_edit = function(profile_id, section) {
  var url = Mailpile.API.U(
    '/profiles/edit/?rid=' + profile_id +
    '&ui_open=' + section +
    '&ui_flags=reload');
  Mailpile.auto_modal({ url: url, method: 'GET' });
};

Mailpile.mailsource_login = function(mailsource_id, event_id) {
  var url = Mailpile.API.U(
    '/settings/set/password/?mailsource=' + mailsource_id);
  Mailpile.auto_modal({
    url: url,
    title: '{{ _("Password Required") }}',
    method: 'POST', sticky: true });
  //Mailpile.cancel_notification(event_id, false, false, true);
};

Mailpile.mailsource_oauth2 = function(mailsource_id, event_id) {
  var url = Mailpile.API.U('/setup/oauth2/?mailsource=' + mailsource_id);
  Mailpile.auto_modal({ url: url, method: 'POST', sticky: true });
  //Mailpile.cancel_notification(event_id, false, false, true);
};

Mailpile.user_host_oauth2 = function(username, hostname, event_id) {
  var url = Mailpile.API.U('/setup/oauth2/?username=' + username + '&hostname=' + hostname);
  Mailpile.auto_modal({ url: url, method: 'POST' });
  //Mailpile.cancel_notification(event_id, false, false, true);
};


Mailpile.notification = function(result) {
  Mailpile.expire_canceled_notifictions();

  // Create CSS friend event_id OR fake-id
  if (result.event_id !== undefined) {
    result.event_id = result.event_id.split('.').join('-');
  } else {
    result.event_id = 'fake-id-' + Math.random().toString(24).substring(5);
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
  if (result.action_cls  === undefined) result.action_cls = '';
  if (result.action_text === undefined) result.action_text = '';
  if (result.icon        === undefined) result.icon = 'icon-inbox';
  if (result.timeout     === undefined) {
    if (result.flags == "c") {
      result.timeout = 8000; // Event complete, timeout quickly
    }
    else {
      result.timeout = 360000000; // 100 hours - await completion
    }
  }

  // Undo & Icon
  if (result.command !== 'tag' && result.type === 'nagify') {
    result.undo = false;
    result.icon = 'icon-signature-unknown';
  }
  else if (result.command === 'tag') {
    result.undo = (result.status == "success");
    result.icon = 'icon-tag';
  }
  else if (result.source && result.source.indexOf('.mail_source.') == 0) {
    // Mail source specific notification logic
    if (!result.data.enabled) return result.event_id;

    if ((result.data.discovery_error == "toomany") &&
        (!result.data.rescan || !result.data.rescan.running) &&
        (!result.data.copying || !result.data.copying.running)) {
      // Mail sources have a limit on how many mailboxes are auto-added
      // during discovery, to prevent runaway bloat if we're pointed at
      // an over-large directory or badly behaved IMAP server. This means
      // users need a UI to raise the limit.
      //
      var lim = result.data.discovery_limit;

      var msg = '{{_("Found over (LIMIT) mailboxes")|escapejs}}';
      var ri = msg.indexOf('(LIMIT)');
      if (ri >= 0) {
        msg = msg.substring(0, ri) + lim + msg.substring(ri+7);
      }

      if (lim < 250) {
        lim = lim * 2;
      } else {
        lim = lim + 250;
      }

      result.message2 = msg;
      result.action_text = '{{_("continue adding more")|escapejs}}';
      result.action_js = (
          ' href="javascript:Mailpile.raise_mail_source_mailbox_limit('
          + '\'' + result.event_id + '\', '
          + '\'' + result.data.id + '\', '
          + lim + ');" ');
    }
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
  // Remove excess whitespace from notification to avoid creating TextNodes in the
  // DOM. Fixes a subtle memory leak (https://github.com/mailpile/Mailpile/issues/1931).
  var notification_html = notification_template(result).trim();
  if ($elem) {
      $elem.replaceWith(notification_html);
  }
  else {
      var bubbles = $('#notification-bubbles');
      if (bubbles.children().length < 15) {
          bubbles.prepend($(notification_html).slideDown('normal'));
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
  cancel = function(delay) {
    // This cancels the event. To avoid weird flickering, if the notification
    // has already been displayed, we leave it up for a little longer.
    if (events[0]) clearTimeout(events[0]);
    setTimeout(function() {
      if (events[1]) Mailpile.cancel_notification(events[1]);
    }, 1250);
  }
  setTimeout(cancel, 120000); // After two minutes just give up...
  return cancel;
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
EventLog.subscribe('.*(Add|Edit)Profile', function(ev) {
  console.log('AddProfile event: ' + ev.data.keygen_started);
  if (ev.data.keygen_started > 0) {
      ev.icon = 'icon-lock-closed';
      var $icon = $('.profile-' + ev.data.profile_id + '-key.icon');
      if (ev.data.keygen_finished > 0) {
          $icon.removeClass('unconfigured');
          $icon.removeClass('icon-clock').removeClass('icon-lock-open');
          $icon.addClass('configured').addClass('icon-lock-closed');
          ev.timeout = 60000; // Keep completed notification up for 1 minute
      }
      else {
          $icon.removeClass('configured');
          $icon.removeClass('icon-lock-open').removeClass('icon-lock-closed');
          $icon.addClass('unconfigured').addClass('icon-clock');
          if (ev.data.keygen_gotlock > 0) {
              ev.action_url = "{{ U('/page/entropy/') }}";
              ev.action_cls = 'auto-modal';
              ev.action_text = '{{_("learn more")|escapejs}}';
              ev.message2 = '{{_("This may take some time!")|escapejs}}';
          }
      }
      Mailpile.notification(ev);
  }
});

EventLog.subscribe('.*mail_source.*', function(ev) {
  //
  // Mail source notifications behave differently depending on which
  // page in the UI you are. On most pages, they behave like normal event
  // notifications, popping up and then disappearing 20 seconds later, and
  // can be silenced for a while by clicking the X.
  //
  // On the profile page however, these messages are sticky and persistent,
  // and they can't be silenced. The rationale for this is that the profile
  // page is the go-to place for account configuration, and the event
  // provides critical information in that context.
  //
  var $src = $('.source-' + ev.data.id);
  var conn_error = (ev.data.connection &&
                    ev.data.connection.error &&
                    ev.data.connection.error[0]);
  if ($src.length > 0) {
    var $icon = $src.find('.icon');
    if ((conn_error &&
         conn_error != 'tls' &&
         conn_error != 'auth' &&
         conn_error != 'oauth2') ||
        (!ev.data.enabled)) {
      $icon.removeClass('configured').removeClass('unconfigured');
      $icon.addClass('misconfigured');
      $src.attr('title', $src.data('title') + '\n\n' +
                         '{{_("Error")|escapejs}}: ' +  ev.message);
    }
    else {
      $icon.removeClass('misconfigured').removeClass('unconfigured');
      $icon.addClass('configured');
    }
    if (ev.data.enabled) Mailpile.uncancel_notification(ev.event_id);
  }
  else {
    ev.timeout = 20000;
  }
  if (((conn_error && conn_error != 'tls') || (!ev.data.enabled)) &&
      (ev.data.profile_id)) {
    ev.action_js = ("onclick=\"Mailpile.profile_edit('"
       + ev.data.profile_id + "','sources');\"");
    ev.action_text = '{{_("edit settings")|escapejs}}';
  }
  if (conn_error == 'tls') {
    ev.action_text = '{{_("details")|escapejs}}';
    ev.action_js = ("onclick=\"Mailpile.certificate_error_details('"
       + ev.data.connection.error[2] + "','" + ev.event_id + "');\"");
  }
  else if (conn_error == 'auth') {
    ev.action_text = '{{_("please log in")|escapejs}}';
    ev.action_js = ("onclick=\"Mailpile.mailsource_login('"
       + ev.data.id + "','" + ev.event_id + "');\"");
    if (!EventLog.seen_event_recently(ev.data.profile_id)) {
      EventLog.just_saw_event(ev.data.profile_id);
      Mailpile.mailsource_login(ev.data.id, ev.event_id);
    }
  }
  else if (conn_error == 'oauth2') {
    ev.action_text = '{{_("grant access")|escapejs}}';
    ev.action_js = ("onclick=\"Mailpile.mailsource_oauth2('"
       + ev.data.id + "','" + ev.event_id + "');\"");
    console.log(ev.data);
    if (!EventLog.seen_event_recently(ev.data.profile_id)) {
       EventLog.just_saw_event(ev.data.profile_id);
       Mailpile.mailsource_oauth2(ev.data.id, ev.event_id);
    }
  }
  ev.icon = 'icon-mailsource';
  Mailpile.notification(ev);
});
EventLog.subscribe('.*compose.Sendit', function(ev) {
  if (ev.data.delivered == ev.data.recipients) {
    ev.icon = 'icon-outbox';
  }
  else if (ev.data.last_error) {
    ev.icon = 'icon-signature-unknown';
    ev.message2 = ev.data.last_error
  }

  if (ev.data.last_error_details) {
    if (ev.data.last_error_details.oauth_error) {
      ev.action_text = '{{_("grant access")|escapejs}}';
      ev.action_js = ("onclick=\"Mailpile.user_host_oauth2('"
         + ev.data.last_error_details.username + "','"
         + ev.data.host + "','"
         + ev.event_id + "');\"");
      Mailpile.uncancel_notification(ev.event_id);
      ev.timeout = 1200000;
    }
    else if (ev.data.last_error_details.tls_error) {
      ev.action_text = '{{_("details")|escapejs}}';
      ev.action_js = ("onclick=\"Mailpile.certificate_error_details('"
         + ev.data.last_error_details.server + "','" + ev.event_id + "');\"");
    }
  }

  Mailpile.notification(ev);
});
EventLog.subscribe('.*HealthCheck', function(ev) {
  if (ev.data.healthy) {
    ev.icon = 'icon-checkmark';
  }
  else {
    ev.icon = 'icon-signature-unknown';
    ev.timeout = 120000;
  }
  Mailpile.notification(ev);
});
