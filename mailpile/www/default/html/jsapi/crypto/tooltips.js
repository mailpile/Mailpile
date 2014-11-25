/* Crypto - Tooltips */

Mailpile.Crypto.Tooltips.KeyScore = function() {
  $('.searchkey-result-score').qtip({
    content: {
      title: false,
      text: function(event, api) {
        return $(this).data('score_reason') + '<small>{{_("Click For Details")}}</small>';
      }
    },
    style: {
      classes: 'qtip-tipped',
      tip: {
        corner: 'left middle',
        mimic: 'left middle',
        border: 0,
        width: 10,
        height: 10
      }
    },
    position: {
      my: 'left center',
      at: 'right center',
			viewport: $(window),
			adjust: {
				x: 5,  y: 2
			}
    },
    show: {
      event: 'mouseenter',
      delay: 0
    },
    hide: {
      event: 'click',
      inactive: 2000
    }
  });
};