var EventLog = {
  eventBindings: [],  // All the subscriptions
  last_ts: Mailpile.local_storage['eventlog_last_ts'] || -1800,
  first_load: true,
  other_tab: 0,
  timeOut: null,
  timer: null
};

EventLog.last_result = function(new_result) {
  if (new_result !== undefined) {
    Mailpile.local_storage['eventlog_last_result'] = JSON.stringify(new_result);
  }
  else {
    return JSON.parse(Mailpile.local_storage['eventlog_last_result'] || '{}');
  }
}

EventLog.pause = function() {
  return EventLog.timer.pause();
};


EventLog.play = function() {
  return EventLog.timer.play();
};


EventLog.request = function(conditions, callback) {
  if (EventLog.first_load) {
    Mailpile.API.logs_events_get({incomplete: true}, EventLog.invoke_callbacks);
    EventLog.first_load = false;
  }
  // We check localStorage here, to see if any other tab has a poll in
  // flight. If it does, we just don't do anything as our localStorage
  // subscription will get the data that way and we don't want too many
  // requests in-flight to the backend at once, both for performance
  // reasons and because of browser simultaneous connection limits.
  var now = new Date().getTime();
  if (now - EventLog.other_tab > 30000) {
    var conditions = conditions || {};
    conditions._error_callback = EventLog.process_error;
    Mailpile.API.logs_events_get(conditions, callback || EventLog.process_result);
  }
  else {
    // Keep checking every 5 seconds, in case the other tab gets closed.
    EventLog.timeOut = setTimeout(function() {EventLog.poll();}, 5000);
  }
};


EventLog.poll = function() {
  //
  // Note: This is unfiltered for these reasons:
  //
  // 1) The eventlog filter language is not flexible enough to watch for all
  //    the different events we need in one call.
  // 2) It also has the issue that if subscriptions change then we need the
  //    ability to immediately terminate the outstanding request and fire off
  //    a new one.
  // 3) Other tabs may rely on us putting things in localStorage that we
  //    ourselves don't care about.
  //
  EventLog.request({
    since: EventLog.last_ts,
    gather: (EventLog.last_ts < 0) ? 0.2 : 1.0,
    wait: 30,
    _timeout: (Mailpile.ajax_timeout * 3)
  });
};


EventLog.invoke_callbacks = function(response) {
  // Update the API CSRF token
  Mailpile.csrf_token = response.state.csrf_token;
  // DEBUGGING: console.log('Update CSRF: ' + Mailpile.csrf_token);

  var event_template = $('#template-event').html();
  if (event_template) {
    event_template = Mailpile.safe_jinjaish_template(event_template);
  }

  // Iterate through the events, calling callbacks...
  var last_ts = response.result.ts;
  for (event in response.result.events) {
    var ev = response.result.events[event];

    for (i in EventLog.eventBindings) {
      var eventBinding = EventLog.eventBindings[i];

      var binding = eventBinding.event;
      var sourceMatched = !binding.source || ev.source.match(new RegExp(binding.source));
      var eventIdMatched = !binding.event_id || (ev.event_id == binding.event_id);
      var flagsMatched = !binding.flags || ev.flags.match(new RegExp(binding.flags));

      if (sourceMatched && eventIdMatched && flagsMatched) {
        eventBinding.callback(ev);
      }
    }

    // This will update any event-log viewer
    if (event_template) {
      var d = new Date(ev.ts * 1000);
      ev.ts_hhmm = (('0' + d.getHours()).substr(-2) + ':' +
                    ('0' + d.getMinutes()).substr(-2));
      var $existing = $('#'+ ev.event_id +'.event-summary');
      if ($existing.data('flags') != ev.flags) {
        $existing.remove();
        $existing = [];
      }
      if ($existing.length > 0) {
        $existing.replaceWith($(event_template(ev)));
      }
      else {
        $('.events-' + ev.flags + ' p:gt(49)').remove();
        $('.events-' + ev.flags).prepend($(event_template(ev)).slideDown());
      }
    }
    last_ts = response.result.ts;
  }
  return last_ts;
};


EventLog.process_error = function(result, textstatus) {
  EventLog.timeOut = setTimeout(function() {EventLog.poll();}, 5000);
};


EventLog.process_result = function(result, textstatus) {
  EventLog.last_ts = EventLog.invoke_callbacks(result);
  EventLog.poll();
  Mailpile.local_storage['eventlog_last_ts'] = EventLog.last_ts;
  EventLog.last_result(result);
};


EventLog.subscribe = function(ev, func, id) {
  // Subscribe a function to an event.
  // Returns a subscription ID.
  if (!$.isFunction(func)) {
    console.log("Can only subscribe functions");
    return false;
  }

  // generate a random id if not specified
  if (typeof id === 'undefined' || id === null) {
    id = Math.random().toString(24).substring(5);
  }

  // Check if event is already subscribed
  var existingEventBinding = this.eventBindings.filter(function (eventBinding) {
    return eventBinding.id === id;
  });

  if (typeof(ev) == "string") {
    ev = {source: ev, event_id: null};
  }

  if (existingEventBinding.length) {
    console.log('Overriding already subscribed event with id: ' + id);
    existingEventBinding[0].event = ev;
    existingEventBinding[0].callback = func;
    return existingEventBinding[0].id;
  }
  else {
    this.eventBindings.push({id: id, event: ev, callback: func});
    return id;
  }
};


EventLog.unsubscribe = function(ev, func_or_id) {
  // Given an event class and a subscription id
  // or a function, will unsubscribe from the event.
  // Returns true if successfully unsubscribed.
  var initialLength = this.eventBindings.length;
  this.eventBindings = this.eventBindings.filter(function (eventBinding) {
    return !(eventBinding.id === func_or_id || eventBinding.callback === func_or_id);
  });

  return this.eventBindings.length < initialLength;
};


EventLog.get_popup_events_cache = function() {
    if (Mailpile.local_storage["seen_popup_events"] === undefined ||
        Mailpile.local_storage["seen_popup_events"] === "") {
        Mailpile.local_storage.setItem("seen_popup_events", JSON.stringify(new Array()));
    }
    return JSON.parse(Mailpile.local_storage["seen_popup_events"]);
}


// The following functions control intermittent popups, mostly
//  for logging into stuff.

EventLog.TIMEOUT_EXPIRE_OLD_EVENTS = 604800; // Once per week
EventLog.TIMEOUT_CHECK_OLD_EVENTS = 3600; // Once per hour

EventLog.seen_event_recently = function(ev) {
    var events = EventLog.get_popup_events_cache();
    for (e in events) {
        if (events[e][0] == ev) {
            return true;
        }
    }
    return false;
};


EventLog.clear_old_events = function(ev) {
    var events = EventLog.get_popup_events_cache();
    var curTime = Math.floor(Date.now() / 1000);
    for (e in events) {
        if (curTime - events[e][1] > EventLog.TIMEOUT_EXPIRE_OLD_EVENTS) {
            events.splice(e, 1);
            Mailpile.local_storage["seen_popup_events"] = JSON.stringify(events);
        }
    }
    return true;
};


EventLog.forget_about_event = function(ev) {
    var events = EventLog.get_popup_events_cache();
    for (e in events) {
        if (events[e][0] == ev) {
            events.splice(e, 1);
            Mailpile.local_storage["seen_popup_events"] = JSON.stringify(events);
            return true;
        }
    }
    return true;
};


EventLog.just_saw_event = function(ev) {
    if (EventLog.seen_event_recently(ev)) {
        return false;
    }
    var events = EventLog.get_popup_events_cache();
    var curTime = Math.floor(Date.now() / 1000);
    events.push([ev, curTime]);
    Mailpile.local_storage["seen_popup_events"] = JSON.stringify(events);
    return true;
};



$(document).ready(function () {
  window.addEventListener('storage', function(evt) {
    // When the localStorage result sharing object gets updated, we parse
    // as if we'd run the API call ourselves.
    if (evt.key == 'eventlog_last_result') {
      EventLog.other_tab = new Date().getTime();
      EventLog.last_ts = EventLog.invoke_callbacks(JSON.parse(evt.newValue));
    }
  }, false);
  window.setTimeout(EventLog.clear_old_events, EventLog.TIMEOUT_CHECK_OLD_EVENTS * 1000);
});
