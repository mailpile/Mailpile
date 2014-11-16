/* UI - Message */

Mailpile.UI.Message.ShowMessage = function(mid) {
  // Mailpile.API.message_get({ mid: '=VCT', _output: 'single.jhtml' }, function(result) { console.log(result); });
  $.ajax({
    url			 : Mailpile.api.message + mid + "/single.jhtml",
    type		 : 'GET',
    dataType : 'json',
    success  : function(response) {
      if (response.result) {
        $('#snippet-' + mid).replaceWith(response.result);
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
  var thread_id = _.keys(Mailpile.instance.messages)[0];
  var msg_top_pos = $('#message-' + thread_id).position().top + 1;
  $('#content-view').scrollTop(msg_top_pos - 150);
  setTimeout(function(){
    $('#content-view').animate({ scrollTop: msg_top_pos }, 350);
  }, 50);
};


/* Thread - iframe styling */
Mailpile.thread_html_iframe = function(element) {
  var new_iframe_height = $(element).contents().height();
  $('.thread-item-html').height(new_iframe_height);
  $(element).contents().find('body div').addClass('thread-item-html-text');
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