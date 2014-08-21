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

  var notification_data = _.extend(result, {
    icon: 'icon-message',
    undo: false
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
    }, 7500);
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
}


var EventLog = {
    eventbindings: [],  // All the subscriptions
    last_ts: -1,
    timer: null,
    cancelwarning: null
};

EventLog.init = function() {
    EventLog.timer = $.timer(EventLog.heartbeat_warning);
    EventLog.timer.set({ time : 22500, autostart : true });
    // make event log start async (e.g. for proper page load event handling)
    setTimeout(EventLog.poll, 500);
};

EventLog.pause = function() {
    return EventLog.timer.pause();
}

EventLog.play = function() {
    return EventLog.timer.play();
}

EventLog.heartbeat_warning = function() {
    console.log('heartbeat_warning() just fired');
    // DISABLED: EventLog.cancelwarning = Mailpile.notification("warning", "Having trouble connecting to Mailpile... will retry in a few seconds.");
    EventLog.poll();
}

EventLog.request = function(conditions, callback) {

    // Hide Connection Down
    if ($('#connection-down').length) {
      $('#connection-down').fadeOut().remove();
    }

    conditions = conditions || {};
    if (!callback) {
        callback = EventLog.process_result;
    }

    Mailpile.API.eventlog_get(conditions, callback);
}

EventLog.poll = function() {
    EventLog.request({since: EventLog.last_ts, wait: 20});     // Request everything new.
};

EventLog.process_result = function(result, textstatus) {
    for (event in result.result.events) {
        var ev = result.result.events[event];
        for (id in EventLog.eventbindings) {
            binding = EventLog.eventbindings[id][0];
            callback = EventLog.eventbindings[id][1];
            if ((!binding.source || ev.source.match(new RegExp("^" + binding.source + "$")))
                    && (!binding.event_id || ev.event_id == binding.event_id)
                    && (!binding.flags || ev.flags.match(new RegExp(binding.flags)))) {
                callback(ev);
            }
        }
        EventLog.last_ts = result.result.ts;
    }
    // HIDDEN
    // console.log("eventlog ---- processed", result.result.count, "results");
    EventLog.timer.stop();
    EventLog.timer.play();
    EventLog.poll();
    if (EventLog.cancelwarning) {
        // DISABLED: EventLog.cancelwarning();
        EventLog.cancelwarning = null;
    }
};


EventLog.subscribe = function(ev, func) {
    // Subscribe a function to an event.
    // Returns a subscription ID.
    if (!$.isFunction(func)) {
        console.log("Can only subscribe functions");
        return false;
    }
    if (typeof(ev) == "string") {
        ev = {source: ev, event_id: null};
    }
    this.eventbindings.push([ev, func]);
    return this.eventbindings.length - 1;
};

EventLog.unsubscribe = function(ev, func_or_id) {
    // Given an event class and a subscription id
    // or a function, will unsubscribe from the event.
    // Returns true if successfully unsubscribed.
    if ($.isFunction(func_or_id)) {
        for (i in this.eventbindings) {
            if (this.eventbindings[i][1] == func_or_id) {
                this.eventbindings.splice(i, 1);
                return true;
            }
        }
    } else {
        this.eventbindings.splice(func_or_id, 1);
        return true;
    }
    return false;
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

$(document).ready(function() {

  // Start
  EventLog.init();

  // HTML5 Browser Notifications
  if (Notification.permission == "granted") {
    $('#notifications-permission-option').text("{{_("Browser notifications allowed")}}")
  }

  $('#notifications-permission-option').click(function() {
    Notification.requestPermission();
  });

});
