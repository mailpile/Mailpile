/* UI - Message */

// SPDX-FileCopyrightText: 2011-2015  Bjarni R. Einarsson, Mailpile ehf and friends
// SPDX-License-Identifier: AGPL-3.0-or-later

Mailpile.UI.Message.ShowMessage = function(mid) {
  var done_loading = Mailpile.notify_working("{{_('Loading message...')|escapejs}}",
                                             500);
  var failed = function() {
    done_loading();
    Mailpile.notification({
      status: 'error',
      message: '{{_("Could not retrieve message")|escapejs}}'
    });
  }
  Mailpile.API.message_get({
    mid: mid,
    _output: 'single.jhtml!minimal',
    _error_callback: failed
  }, function(response) {
    if (response.result) {
      done_loading();
      $('#message-' + mid).replaceWith(response.result);
      Mailpile.UI.prepare_new_content($('#message-' + mid));
    }
    else failed();
  });
};


Mailpile.UI.Message.ScrollToMessage = function() {

  var msg_top_pos = 0;
  var check_new = $('#content-view, #content-tall-view').find('div.new');

  if (check_new.length) {
    var unread_thread_id = $(check_new[0]).data('mid');
    msg_top_pos = $('#message-' + unread_thread_id).position().top + 1;
  } 
  else {
    var full_message = $('#content-view, #content-tall-view').find('div.thread-message');
    if (full_message.length) {
      var thread_id = $(full_message[0]).data('mid');
      msg_top_pos = $('#message-' + thread_id).position().top + 1;
    }
  }

  // Scroll To
  setTimeout(function(){
    $('#content-view, #content-tall-view').animate({ scrollTop: msg_top_pos }, 450);
  }, 50);
};


Mailpile.UI.Message.Draggable = function(element) {
  $(element).draggable({
    containment: 'window',
    appendTo: 'body',
    cursor: 'move',
    scroll: false,
    revert: false,
    opacity: 1,
    helper: function(event) {
      return $('<div class="pile-results-drag ui-widget-header"><span class="icon-inbox"></span> Moving Thread</div>');
    },
    start: function(event, ui) {
      Mailpile.ui_in_action += 1;
    },
    stop: function(event, ui) {
      setTimeout(function() { Mailpile.ui_in_action -= 1; }, 250);
    }
  });
};
