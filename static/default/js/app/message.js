/* message.js */

$(document).on('click', '.message-action-forward', function() {
  var mid = $(this).parent().parent().data('mid');
  $.ajax({
    url      : '/api/0/message/forward/',
    type     : 'POST',
    data     : { mid: mid },
    success  : function(response) {
      if (response.status === 'success') {
        window.location.href = mailpile.urls.message_draft + response.result.created + '/';
      } else {
        mailpile.notification(response.status, response.message);
      }
    }
  });
});

$(document).on('click', '.message-action-inbox', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  mailpile.tag_add_delete(['inbox'], ['spam', 'trash'], mid, function(result) {
    window.location.href = '/in/inbox/';
  });
});

$(document).on('click', '.message-action-spam', function() {
  var mid = $(this).parent().parent().parent().parent().data('mid');
  mailpile.tag_add_delete(['spam'], ['trash', 'inbox'], mid, function() {
    window.location.href = '/in/inbox/';
  });
});

$(document).on('click', '.message-action-unthread', function() {
  var mid = $(this).parent().parent().data('mid');
  console.log('This will Unthread a single message'); 
});

$(document).on('click', '.message-action-trash', function() {
  var mid = $(this).parent().parent().data('mid');
  mailpile.tag_add_delete(['trash'], ['spam', 'inbox'], mid, function() {
    window.location.href = '/in/inbox/';
  });
});