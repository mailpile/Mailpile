/* Tags - Tooltips */

Mailpile.Tags.Tooltips.CardSubtags = function() {
  $('.tag-card-subtags').qtip({
    content: {
      title: false,
      text: function(event, api) {
        Mailpile.API.tags_get({ tid: $(this).data('tid').toString() },
                              function(response) {
          var tooltip_template = _.template($('#tooltip-tag-subtags').html());
          var tooltip_data = response.result.tags[0];
          api.set('content.text', tooltip_template(tooltip_data));
        });
        return "...";
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
    show: { delay: 100 },
    hide: { fixed: true, delay: 350 }
  });
};
