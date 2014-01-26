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