/* UI - Message */

Mailpile.UI.Message.ShowMessage = function(mid) {
  // Mailpile.API.message_get({ mid: '=VCT', _output: 'single.jhtml' }, function(result) { console.log(result); });
  $.ajax({
    url			 : Mailpile.api.message + mid + "/single.jhtml",
    type		 : 'GET',
    dataType : 'json',
    success  : function(response) {
      if (response.result) {
        $('#message-' + mid).replaceWith(response.result);
        Mailpile.Message.Tooltips.Crypto();
        Mailpile.Message.Tooltips.Attachments();
      }
    },
    error: function() {
      Mailpile.notification({status: 'error', message: '{{_("Could not retrieve message")|escapejs}}' });
    }
  });

}
;


Mailpile.UI.Message.ScrollToMessage = function() {

  var msg_top_pos = 0;
  var check_new = $('#content-view').find('div.new');

  if (check_new.length) {
    var unread_thread_id = $(check_new[0]).data('mid');
    msg_top_pos = $('#message-' + unread_thread_id).position().top + 1;
  } 
  else {
    var full_message = $('#content-view').find('div.thread-message');
    if (full_message.length) {
      var thread_id = $(full_message[0]).data('mid');
      msg_top_pos = $('#message-' + thread_id).position().top + 1;
    }
  }

  // Scroll To
  setTimeout(function(){
    $('#content-view').animate({ scrollTop: msg_top_pos }, 450);
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
  
      // FIXME: This should all come from the DOM; and a checkbox needs to
      //        live in the DOM as well for the standard drag/drop code to
      //        work.

      // Add Draggable MID
      var mid = location.href.split("thread/=")[1].split("/")[0];
      Mailpile.bulk_cache_add('messages_cache', mid);
  
      // Update Bulk UI
      // Style & Select Checkbox
    },
    stop: function(event, ui) {
      setTimeout(function() { Mailpile.ui_in_action -= 1; }, 250);
    }
  });
};
