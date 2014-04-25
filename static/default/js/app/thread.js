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


/* Thread - iframe styling */
MailPile.prototype.thread_html_iframe = function(element) {

  var new_iframe_height = $(element).contents().height();
  $('.thread-item-html').height(new_iframe_height);

  $(element).contents().find('body div').addClass('thread-item-html-text');
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

/* Thread - Show Tags In Converstation */
$(document).on('click', '.show-thread-tags', function() {

 var options = {
   backdrop: true,
   keyboard: true,
   show: true,
   remote: false
 };

 $('#modal-full .modal-title').html($('#thread-tags').data('modal_title'));
 $('#modal-full .modal-body').html($('#thread-tags').html());
 $('#modal-full').modal(options);
});

/* Thread - Show Security */
$(document).on('click', '.show-thread-security', function() {
  
  alert('FIXME: Show details about security of thread');
});

/* Thread - Show Metadata Info */
$(document).on('click', '.show-thread-message-metadata-details', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  var target = '#metadata-details-' + mid;
  if ($(target).css('display') === 'none') {
    $(target).fadeIn();
    $(this).css('color', '#4d4d4d');
  }
  else {
    $(target).fadeOut();    
    $(this).css('color', '#ccc');
  }
});


/* Thread - Expand Snippet */
$(document).on('click', 'div.thread-snippet', function(e) {  
  var mid = $(this).data('mid');
  if (e.target.href === undefined && $(e.target).data('expand') !== 'no') {
    mailpile.render_thread_message(mid);
  }
});


/* Thread - Message Quote */
$(document).on('click', '.thread-message-actions-quote', function() {
  var mid = $(this).parent().parent().data('mid');
  $('#message-' + mid).find('.thread-item-quote').removeClass('hide');
  $('#message-' + mid).find('.thread-item-signature').removeClass('hide');
  $(this).parent().hide();
});


/* Thread - Might Move to Global Location / Abstraction */
$(document).on('click', '.dropdown-toggle', function() {
  $(this).find('.icon-arrow-right').removeClass('icon-arrow-right').addClass('icon-arrow-down');
});


/* Thread - Add Contact */
$(document).on('click', '.message-action-add-contact', function() {

  var mid = $(this).parent().parent().data('mid');
  var name = $(this).data('name');
  var address = $(this).data('address');
  var signature = 'FIXME: ' + $('#message-' + mid).find('.thread-item-signature').html();

  var modal_html = $("#modal-add-contact").html();
  $('#modal-full').html(_.template(modal_html, {}));
  $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });

  // Add Values
  $('.contact-add-name').val(name);
  $('.contact-add-email').val(address);
  $('.contact-add-signature').html(signature);
  $('.contact-add-mid').val(mid);
});


/* Thread - Add Contact Form */
$(document).on('submit', '#form-add-contact-modal', function(e) {
  e.preventDefault();
  mailpile.contact_add('#form-add-contact-modal', function() {    
    // Hide Modal
    $('#modal-full').modal('hide');
    // Remove Button
    $('#message-' + mid).find('.message-action-add-contact').parent().remove();
  });
});


/* Thread - Import Key */
$(document).on('click', '.message-action-import-key', function() {
  
  var options = {
    backdrop: true,
    keyboard: true,
    show: true,
    remote: false
  };

  $('#modal-full .modal-title').html('<span class="icon-key"></span> Import Key');
  $('#modal-full .modal-body').html('<p>Eventually this will import a PGP key to a contact.</p>');
  $('#modal-full').modal(options);  
  
});


/* Thread Tooltips */
$(document).ready(function() {

  // Thread Scroll to Message
  if (location.href.split("thread/=")[1]) {

    // Scroll to Message
    var thread_id = location.href.split("thread/=")[1].split("/")[0];
    var msg_top_pos = $('#message-' + thread_id).position().top;
    $('#content-view').scrollTop(msg_top_pos - 150);
    setTimeout(function(){
      $('#content-view').animate({ scrollTop: msg_top_pos }, 350);
    }, 50);
    
    // Show Tooltips
    mailpile.thread_initialize_tooltips();
  }

});

