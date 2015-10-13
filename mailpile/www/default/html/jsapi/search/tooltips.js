/* Search - Tooltips */

Mailpile.Search.Tooltips.MessageTags = function() {
  $('.pile-message-tag').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var mid = $(this).data('mid').toString();
        var tid = $(this).data('tid').toString();
        Mailpile.API.tags_get({ tid: tid }, function(response) {
          var tooltip_template = _.template($('#tooltip-pile-tag-details').html());
          var tooltip_data = response.result.tags[0];
          tooltip_data['mid'] = mid;
          api.set('content.text', tooltip_template(tooltip_data));
        });
        return "...";
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
      adjust: {x: 7, y: 2},
      effect: false
    },
    show: { delay: 100 },
    hide: { fixed: true, delay: 350 }
  });
};
