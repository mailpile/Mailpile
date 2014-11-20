/* Crypto - Tooltips */

Mailpile.Crypto.Tooltips.KeyScore = function() {
  $('.searchkey-result-score').qtip({
    content: {
      title: true,
      text: function(e, api) {
        $target = $(e.target);
      }
    },
    style: {
     tip: {
        corner: 'bottom center',
        mimic: 'bottom center',
        border: 0,
        width: 10,
        height: 10
      },
      classes: 'qtip-contact-details'
    },
    position: {
      my: 'bottom center',
      at: 'bottom center',
			viewport: $(window),
			adjust: {
				x: 5,  y: -25
			}
    },
    show: {
      event: 'mouseenter',
      delay: 0
    },
    hide: {
      event: true,
      inactive: 750
    }
  });
};