/* Tags - Tooltips */

Mailpile.Tags.Tooltips.CardSubtags = function() {
  $('.tag-card-subtags').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var tag = _.findWhere(Mailpile.instance.tags, {tid: $(this).data('tid')});
        var tooltip_template = _.template($('#tooltip-tag-subtags').html());
        return tooltip_template({ tag: tag });
      }
    },
    style: {
     tip: {
        target: $(this),
        border: 0,
        width: 10,
        height: 10
      },
      classes: 'qtip-tag-details'
    },
    position: {
      my: 'top center',
      at: 'bottom center',
			viewport: $('#content-view'),
			adjust: {
				x: -5,  y: 0
			}
    },
    show: {
      delay: 50
    },
    hide: {
      event: false,
      inactive: 1000
    }
  });
};