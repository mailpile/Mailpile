var EventLog = {
  eventbindings: [],  // All the subscriptions
  last_ts: -1,
  timer: null,
  cancelwarning: null
};


EventLog.pause = function() {
  return EventLog.timer.pause();
};


EventLog.play = function() {
  return EventLog.timer.play();
};


EventLog.heartbeat_warning = function() {
  console.log('EventLog.heartbeat_warning()');
  // DISABLED: EventLog.cancelwarning = Mailpile.notification("warning", "Having trouble connecting to Mailpile... will retry in a few seconds.");
  EventLog.poll();
};


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
};


EventLog.poll = function() {
  // Request everything new
  EventLog.request({since: EventLog.last_ts, wait: 20});
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