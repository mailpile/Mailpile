var EventLog = {
  eventbindings: [],  // All the subscriptions
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
    _timeout: 31000
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
    for (id in EventLog.eventbindings) {
      binding = EventLog.eventbindings[id][0];
      callback = EventLog.eventbindings[id][1];
      if ((!binding.source || ev.source.match(new RegExp(binding.source)))
          && (!binding.event_id || ev.event_id == binding.event_id)
          && (!binding.flags || ev.flags.match(new RegExp(binding.flags)))) {
        callback(ev);
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


$(document).ready(function () {
  window.addEventListener('storage', function(evt) {
    // When the localStorage result sharing object gets updated, we parse
    // as if we'd run the API call ourselves.
    if (evt.key == 'eventlog_last_result') {
      EventLog.other_tab = new Date().getTime();
      EventLog.last_ts = EventLog.invoke_callbacks(JSON.parse(evt.newValue));
    }
  }, false);
});
