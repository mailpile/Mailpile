MailPile.prototype.thread_initialize_tooltips = function() {

  $('.thread-item-crypto-info').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var html = '<div>\
          <h4 class="' + $(this).data('crypto_color') + '">\
            <span class="' + $(this).data('crypto_icon') + '"></span>' + $(this).attr('title') + '\
          </h4>\
          <p>' + $(this).data('crypto_message') + '</p>\
          </div>';
        return html;
      }
    },
    style: {
      classes: 'qtip-thread-crypto',
      tip: {
        corner: 'bottom right',
        mimic: 'bottom right',
        border: 1,
        width: 12,
        height: 12,
        corner: true
      }
    },
    position: {
      my: 'bottom right',
      at: 'top left',
			viewport: $(window),
			adjust: {
				x: 7, y: -5
			}
    },
    show: {
      delay: 100
    },
    hide: {
      delay: 250
    }
  });
};