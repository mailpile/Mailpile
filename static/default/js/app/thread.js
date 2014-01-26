MailPile.prototype.view = function(idx, msgid) {
	this.json_get("view", {"idx": idx, "msgid": msgid}, function(data) {
		if ($("#results").length === 0) {
			$("#content").prepend('<table id="results" class="results"><tbody></tbody></table>');
		}
		$("#results").empty();
	});
};

MailPile.prototype.render_thread_message = function(mid) {
  
  $.ajax({
    url			 : mailpile.api.message + mid + "/single.jhtml",
    type		 : 'GET',
    dataType : 'json',
    success  : function(response) {
      if (response.results) {
        $('#snippet-' + mid).replaceWith(response.results[0]);
      }
    },
    error: function() {
      mailpile.notification('error', 'Could not retrieve message');
    }
  });

};

/* Thread - Show People In Conversation */
$(document).on('click', '.show-thread-people', function() {

  alert('FIXME: Show all people in conversation');
});

/* Thread - Show Security */
$(document).on('click', '.show-thread-security', function() {
  
  alert('FIXME: Show details about security of thread');
});

/* Thread - Show Metadata Info */
$(document).on('click', '.show-thread-message-metadata-details', function() {
  $('#metadata-details-' + $(this).parent().parent().parent().parent().data('mid')).fadeIn();
});


/* Thread - Expand Snippet */
$(document).on('click', 'div.thread-snippet', function(e) {  
  var mid = $(this).data('mid');
  if (e.target.href === undefined && $(e.target).data('expand') !== 'no') {
    mailpile.render_thread_message(mid);
  }
});


/* Thread - Message Quote Show */
$(document).on('click', '.thread-item-quote-show', function() {
  var quote_id = $(this).data('quote_id');
  var quote_text = $('#message-quote-text-' + quote_id).html();
  $('#message-quote-' + quote_id).html(quote_text);
});


/* Thread - Might Move to Global Location / Abstraction */
$(document).on('click', '.dropdown-toggle', function() {
  console.log('toggle da bizzle');
  $(this).find('.icon-arrow-right').removeClass('icon-arrow-right').addClass('icon-arrow-down');
});


/* Thread Tooltips */
$(document).ready(function() {

  
  $('.thread-item-crypto-info').qtip({
    style: {
      classes: 'qtip-tipped'
    },
    position: {
      my: 'bottom center',
      at: 'top left',
			viewport: $(window),
			adjust: {
				x: 25,  y: 0
			}
    },
    show: {
      delay: 250
    },
    hide: {
      delay: 250
    }
  });


  // Thread Scroll to Message
  if (location.href.split("thread/=")[1]) {
    var thread_id = location.href.split("thread/=")[1].split("/")[0];
    var msg_top_pos = $('#message-' + thread_id).position().top;
    $('#content-view').scrollTop(msg_top_pos - 150);
    setTimeout(function(){
      $('#content-view').animate({ scrollTop: msg_top_pos }, 350);
    }, 50)
  }


});

