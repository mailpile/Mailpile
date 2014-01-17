// Non-exposed functions: www, setup
$(document).ready(function() {


  $('.topbar-nav a').qtip({
    style: {
     tip: {
        corner: 'top center',
        mimic: 'top center',
        border: 0,
        width: 10,
        height: 10
      },
      classes: 'qtip-tipped'
    },
    position: {
      my: 'top center',
      at: 'bottom center',
			viewport: $(window),
			adjust: {
				x: 0,  y: 5
			}
    },
    show: {
      delay: 350
    }
  });


  $('a.bulk-action').qtip({
    style: {
      classes: 'qtip-tipped'
    },
    position: {
      my: 'top center',
      at: 'bottom center',
			viewport: $(window),
			adjust: {
				x: 0,  y: 5
			}
    }
  });


  $('.message-privacy-state').qtip({
    style: {
     tip: {
        corner: 'right center',
        mimic: 'right center',
        border: 0,
        width: 10,
        height: 10
      },
      classes: 'qtip-tipped'
    },
    position: {
      my: 'right center',
      at: 'left center',
			viewport: $(window),
			adjust: {
				x: -5,  y: 0
			}
    },
    show: {
      delay: 50
    },
    events: {
      show: function(event, api) {

        $('.compose-to').css('background-color', '#fbb03b');
        $('.compose-cc').css('background-color', '#fbb03b');           
        $('.compose-bcc').css('background-color', '#fbb03b');
        $('.compose-from').css('background-color', '#fbb03b');
        $('.compose-subject').css('background-color', '#fbb03b');

        $('.compose-message').css('background-color', '#a2d699');
        $('.compose-attachments').css('background-color', '#a2d699');

        console.log('Checking this out'); 
      },
      hide: function(event, api) {

        $('.compose-to').css('background-color', '#ffffff');
        $('.compose-cc').css('background-color', '#ffffff');           
        $('.compose-bcc').css('background-color', '#ffffff');
        $('.compose-from').css('background-color', '#ffffff');
        $('.compose-subject').css('background-color', '#ffffff');

        $('.compose-message').css('background-color', '#ffffff');
        $('.compose-attachments').css('background-color', '#ffffff');
        
      }
    }
  });


  $('.compose-to-email').qtip({
    content: {
      text: 'Email This Address'
    },
    style: {
      classes: 'qtip-tipped'
    },
    position: {
      my: 'bottom center',
      at: 'top center',
			viewport: $(window),
			adjust: {
				x: 0,  y: 0
			}
    },
    show: {
      delay: 500
    }
  });


});