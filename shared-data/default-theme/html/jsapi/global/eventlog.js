var EventLog = {
  eventbindings: [],  // All the subscriptions
  last_ts: Mailpile.local_storage['eventlog_last_ts'] || -1800,
  first_load: true,
  timer: null
};


EventLog.pause = function() {
  return EventLog.timer.pause();
};


EventLog.play = function() {
  return EventLog.timer.play();
};


EventLog.request = function(conditions, callback) {
  if (EventLog.first_load) {
    Mailpile.API.eventlog_get({incomplete: true}, EventLog.invoke_callbacks);
    EventLog.first_load = false;
  }
  var conditions = conditions || {};
  conditions._error_callback = EventLog.process_error;
  Mailpile.API.eventlog_get(conditions, callback || EventLog.process_result);
};


EventLog.poll = function() {
  // BRE: disabled the filtering for now, as the eventlog filter language
  //      is not flexible enough to watch for all the different events
  //      we need in one call. It also has the issue that if subscriptions
  //      change then we need the ability to immediately terminate the
  //      outstanding request and fire off a new one. So for now we just
  //      use the firehose, but increase the gather time to 1 second.
  //
  // Request news about updates to the mail sources and command cache
  //var source_re = '~(.mail_source|.command_cache';
  //
  // ... and any other things we consider exciting
  //for (id in EventLog.eventbindings) {
  //   binding = EventLog.eventbindings[id][0];
  //   source_re += '|' + binding.source;
  //}
  //source_re += ')';

  EventLog.request({
  //source: source_re,
    since: EventLog.last_ts,
    gather: (EventLog.last_ts < 0) ? 0.2 : 1.0,
    wait: 30,
    _timeout: 31000
  });
};


EventLog.invoke_callbacks = function(response) {
  // Update the API CSRF token
  Mailpile.csrf_token = response.state.csrf_token;

  // Iterate through the events, calling callbacks...
  var last_ts = response.result.ts;
  for (event in response.result.events) {
    var ev = response.result.events[event];
    for (id in EventLog.eventbindings) {
      binding = EventLog.eventbindings[id][0];
      callback = EventLog.eventbindings[id][1];
      if ((!binding.source || ev.source.match(new RegExp(binding.source)))
          && (!binding.event_id || ev.event_id == binding.event_id)
          && (!binding.flags || ev.flags.match(new RegExp(binding.flags)))) {
        callback(ev);
      }
    }
    last_ts = response.result.ts;
  }
  return last_ts;
};


EventLog.process_error = function(result, textstatus) {
  setTimeout(function() {EventLog.poll();}, 5000);
};


EventLog.process_result = function(result, textstatus) {
  EventLog.last_ts = EventLog.invoke_callbacks(result);
  EventLog.poll();
  Mailpile.local_storage['eventlog_last_ts'] = EventLog.last_ts;
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
