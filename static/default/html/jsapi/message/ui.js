
/* Message - drag thread to Sidebar */
Mailpile.Message.UI.Draggable = function() {
  $('div.thread-draggable').draggable({
    containment: "body",
    appendTo: 'body',
    cursor: 'move',
    scroll: false,
    revert: false,
    opacity: 1,
    helper: function(event) {
      return $('<div class="pile-results-drag ui-widget-header"><span class="icon-message"></span> Moving Thread</div>');
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