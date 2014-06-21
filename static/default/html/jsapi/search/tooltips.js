/* Search - Tooltips */
$(document).ready(function() {

  $('.pile-message-tag').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var tooltip_data = _.findWhere(mailpile.instance.tags, { tid: $(this).data('tid').toString() });              
        tooltip_data['mid'] = $(this).data('mid');
        return  _.template($('#tooltip-pile-tag-details').html(), tooltip_data);
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
      event: 'click',
      delay: 150
    },
    hide: {
      event: false,
      inactive: 700
    }
  });

});