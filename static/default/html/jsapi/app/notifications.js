/* Notifications - UI notification at top of window */
Mailpile.notification = function(status, message_text, complete, complete_action) {
    var default_messages = {
        "success" : "Success, we did exactly what you asked.",
        "info"    : "Here is a basic info update",
        "debug"   : "What kind of bug is this bug, it's a debug",
        "warning" : "This here be a warnin to you, just a warnin mind you",
        "error"   : "Whoa cowboy, you've mozied on over to an error"
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

    } else if (complete == 'hide') {
        message.delay(5000).fadeOut('normal', function() {
            message.find('span.message-text').empty();
        });
    } else if (complete == 'redirect') {
        setTimeout(function() { window.location.href = complete_action }, 5000);
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
    // console.log('heartbeat_warning() just fired');
    // DISABLED: EventLog.cancelwarning = Mailpile.notification("warning", "Having trouble connecting to Mailpile... will retry in a few seconds.");
    EventLog.poll();
}

EventLog.request = function(conditions, callback) {
    conditions = conditions || {};
    if (!callback) {
        callback = EventLog.process_result;
    }

    Mailpile.API.eventlog_get(conditions, callback);
}

EventLog.poll = function() {
    // console.log('poll() just fired');
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
$(document).on('click', '.message-close', function() {
  $(this).parent().fadeOut(function() {
  });
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
