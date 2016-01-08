/* UI - Tooltips */
Mailpile.UI.content_setup.push(function($content) {

  // Topbar navigation tooltips
  $content.find('.topbar-nav a').qtip({
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

  // Bulk action tooltips
  $content.find('.bulk-actions ul li a').qtip({
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

  // Email composition tooltips
  $content.find('.compose-to-email').qtip({
    content: {
      title: false,
      text: function(event, api) {
        return '{{_("Compose to:")|escapejs}} ' + $(this).attr('href').replace('mailto:', '');
      }
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
      delay: 450
    }
  });

});
