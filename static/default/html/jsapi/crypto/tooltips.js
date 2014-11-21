/* Crypto - Tooltips */

Mailpile.Crypto.Tooltips.KeyScore = function() {
  $('.searchkey-result-score').qtip({
    style: {
      classes: 'qtip-tipped',
      tip: {
        corner: 'top center',
        mimic: 'top center',
        border: 0,
        width: 10,
        height: 10
      }
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
      inactive: 500
    }
  });
};