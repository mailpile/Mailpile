/* message.js */

$(document).on('click', '.message-action-forward', function() {

  var mid = $(this).parent().parent().data('mid');

  new_mailpile.api.message_forward(mid, function(result){
    console.log('inside the callback');
    console.log(result); 
  });

});

$(document).on('click', '.message-action-inbox', function() {
  alert('This will move a single message to Inbox');
});

$(document).on('click', '.message-action-spam', function() {
  alert('This will move a single message to Spam');
});

$(document).on('click', '.message-action-unthread', function() {
  alert('This will unthread a message from current thread');
});

$(document).on('click', '.message-action-trash', function() {
  alert('This will move a single message to Trash');
});