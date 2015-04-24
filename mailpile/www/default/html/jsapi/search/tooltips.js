/* Search - Tooltips */

Mailpile.Search.Tooltips.MessageTags = function() {
  $('.pile-message-tag').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var tooltip_data = _.findWhere(Mailpile.instance.tags, { tid: $(this).data('tid').toString() });              
        tooltip_data['mid'] = $(this).data('mid');
        var tooltip_template = _.template($('#tooltip-pile-tag-details').html());
        return tooltip_template(tooltip_data);
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
      delay: 50
    },
    hide: {
      event: false,
      inactive: 700
    }
  });
};