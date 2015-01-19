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
      Mailpile.notification({status: 'error', message: 'Could not retrieve message'});
    }
  });

};


Mailpile.UI.Message.ScrollToMessage = function() {

  $('#content-view').scrollTop(msg_top_pos - 150);
  var check_new = $('#content-view').find('div.new');

  if (check_new.length) {
    var unread_thread_id = $(check_new[0]).data('mid');
    var msg_top_pos = $('#message-' + unread_thread_id).position().top + 1;
  } 
  else {
    var thread_id = _.keys(Mailpile.instance.messages)[0];
    var msg_top_pos = $('#message-' + thread_id).position().top + 1;
  }

  // Scroll To
  setTimeout(function(){
    $('#content-view').animate({ scrollTop: msg_top_pos }, 450);
  }, 50);
};


Mailpile.UI.Message.Draggable = function(element) {
  $(element).draggable({
    containment: 'body',
    appendTo: 'body',
    cursor: 'move',
    scroll: false,
    revert: false,
    opacity: 1,
    helper: function(event) {
      return $('<div class="pile-results-drag ui-widget-header"><span class="icon-inbox"></span> Moving Thread</div>');
    },
    start: function(event, ui) {
  
      // Add Draggable MID
      var mid = location.href.split("thread/=")[1].split("/")[0];
      Mailpile.bulk_cache_add('messages_cache', mid);
  
      // Update Bulk UI
    	// Style & Select Checkbox
    },
    stop: function(event, ui) {}
  });
};