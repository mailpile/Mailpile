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

MailPile.prototype.thread_initialize_tooltips = function() {

  $('.thread-item-crypto-info').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var html = '<div>\
          <h4 class="' + $(this).data('crypto_color') + '">\
            <span class="' + $(this).data('crypto_icon') + '"></span>' + $(this).attr('title') + '\
          </h4>\
          <p>' + $(this).data('crypto_message') + '</p>\
          </div>';
        return html;
      }
    },
    style: {
      classes: 'qtip-thread-crypto',
      tip: {
        corner: 'bottom center',
        mimic: 'bottom center',
        border: 0,
        width: 10,
        height: 10
      }
    },
    position: {
      my: 'bottom center',
      at: 'top left',
			viewport: $(window),
			adjust: {
				x: 7,  y: -4
			}
    },
    show: {
      delay: 150
    },
    hide: {
      delay: 250
    }
  });
};


/* Thread - Show People In Conversation */
$(document).on('click', '.show-thread-people', function() {

 //alert('FIXME: Show all people in conversation');
 var options = {
   backdrop: true,
   keyboard: true,
   show: true,
   remote: false
 };

 $('#modal-full .modal-title').html($('#thread-people').data('modal_title'));
 $('#modal-full .modal-body').html($('#thread-people').html());
 $('#modal-full').modal(options);

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
  $(this).find('.icon-arrow-right').removeClass('icon-arrow-right').addClass('icon-arrow-down');
});


/* Thread Tooltips */
$(document).ready(function() {

  // Thread Scroll to Message
  if (location.href.split("thread/=")[1]) {
    
    var thread_id = location.href.split("thread/=")[1].split("/")[0];
    var msg_top_pos = $('#message-' + thread_id).position().top;
    $('#content-view').scrollTop(msg_top_pos - 150);
    setTimeout(function(){
      $('#content-view').animate({ scrollTop: msg_top_pos }, 350);
    }, 50);
    
    mailpile.thread_initialize_tooltips();
  }

});

