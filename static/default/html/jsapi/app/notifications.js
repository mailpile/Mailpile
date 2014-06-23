MailPile.prototype.notification = function(status, message_text, complete, complete_action) {
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
    eventbindings: {},  // All the subscriptions
    last_ts: -1,
    timer: null,
    cancelwarning: null
};

EventLog.init = function() {
    $('.message-close').on('click', function() {
        $(this).parent().fadeOut();
    });

    EventLog.timer = $.timer(EventLog.heartbeat_warning);
    EventLog.timer.set({ time : 22000, autostart : true });
    EventLog.poll();
};

EventLog.pause = function() {
    return EventLog.timer.pause();
}

EventLog.play = function() {
    return EventLog.timer.play();
}

EventLog.heartbeat_warning = function() {
    EventLog.cancelwarning = mailpile.notification("warning", "Having trouble connecting to Mailpile... will retry in a few seconds.");
    EventLog.poll();
}

EventLog.request = function(conditions) {
    conditions = conditions || {};
    if (!conditions.callback) {
        conditions.callback = EventLog.process_result;
    }

    new_mailpile.api.eventlog(
        conditions.privatedata, // private_data
        conditions.source,      // source
        conditions.flag,        // require a flag
        conditions.allflags,    // match all flags
        conditions.since,       // since when?
        conditions.filter,      // filter?
        conditions.incomplete,  // incomplete events only?
        conditions.wait,        // wait for new data?
        conditions.callback     // callback
    );
}

EventLog.poll = function() {
    EventLog.request({since: EventLog.last_ts, wait: 20});     // Request everything new.
};

EventLog.process_result = function(result, textstatus) {
    for (event in result.result.events) {
        var ev = result.result.events[event];
        for (binding in EventLog.eventbindings) {
            if (ev.source.match(new RegExp("^" + binding + "$"))) {
                EventLog.firebindings(binding, ev);
            }
        }
        EventLog.last_ts = result.result.ts;
    }
    console.log("eventlog ---- processed", result.result.count, "results");
    EventLog.timer.stop();
    EventLog.timer.play();
    EventLog.poll();
    if (EventLog.cancelwarning) {
        EventLog.cancelwarning();
        EventLog.cancelwarning = null;
    }
};

EventLog.firebindings = function(binding, ev) {
    for (fun in this.eventbindings[binding]) {
        this.eventbindings[binding][fun](ev);
    }
}

EventLog.subscribe = function(ev, func) {
    // Subscribe a function to an event.
    // Returns a subscription ID.
    if (!this.eventbindings[ev]) {
        this.eventbindings[ev] = [];
    }
    if (!$.isFunction(func)) {
        console.log("Can only subscribe functions");
        return false;
    }
    this.eventbindings[ev].push(func);
    return this.eventbindings[ev].length - 1;
};

EventLog.unsubscribe = function(ev, func_or_id) {
    // Given an event class and a subscription id
    //   or a function, will unsubscribe from the 
    //   event.
    // Returns true if successfully unsubscribed.
    if ($.isFunction(func_or_id)) {
        for (i in this.eventbindings[ev]) {
            if (this.eventbindings[ev][i] == func_or_id) {
                this.eventbindings[ev].splice(i, 1);
                return true;
            }
        }
    } else {
        this.eventbindings[ev].splice(func_or_id, 1);
        return true;
    }
    return false;
};


$(document).ready(function() {
    /* Message Close */
    $('.message-close').on('click', function() {
        $(this).parent().fadeOut(function() {
            //$('#header').css('padding-top', statusHeaderPadding());
        });
    });

    EventLog.init();

    if (window.webkitNotifications.checkPermission() == 0) {
        $('#notifications-permission-option').text("{{_("Browser notifications allowed")}}")
    }
    $('#notifications-permission-option').click(function() {
        window.webkitNotifications.requestPermission();
    });
});
