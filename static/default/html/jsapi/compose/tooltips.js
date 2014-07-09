Mailpile.tooltip_compose_crypto_signature = function() {
  $('.compose-crypto-signature').qtip({
    content: {
      title: false,
      text: function(event, api) {
        $(this).find('text').removeClass('hide');
        var html = '<div>\
          <h4 class="' + $(this).data('crypto_color') + '">' + $(this).html().replace(' hide', '') + '</h4>\
          <p>' + $(this).attr('title') + '</p>\
          </div>';
        return html;
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
      classes: 'qtip-thread-crypto'
    },
    position: {
      my: 'bottom center',
      at: 'top center',
			viewport: $(window),
			adjust: {
				x: -5,  y: 0
			}
    },
    show: {
      delay: 50
    },
    events: {
      show: function(event, api) {}
    }
  });
};


Mailpile.tooltip_compose_crypto_encryption = function() {
  $('.compose-crypto-encryption').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var html = '<div>\
          <h4 class="' + $(this).data('crypto_color') + '">' + $(this).html().replace(' hide', '') + '</h4>\
          <p>' + $(this).attr('title') + '</p>\
          </div>';
        return html;
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
      classes: 'qtip-thread-crypto'
    },
    position: {
      my: 'bottom center',
      at: 'top center',
			viewport: $(window),
			adjust: {
				x: -5,  y: 0
			}
    },
    show: {
      delay: 50
    },
    events: {
      show: function(event, api) {
        // FIXME: Replace colors with dynamic JSAPI values
        $('.select2-choices').css('border-color', '#fbb03b');
        $('.compose-from').css('border-color', '#fbb03b');
        $('.compose-subject input[type=text]').css('border-color', '#fbb03b');

        if ($('#compose-encryption').val() === 'encrypt') {
          var encrypt_color = '#a2d699';
        } else {
          var encrypt_color = '#fbb03b';
        }

        $('.compose-options-crypto').css('border-color', encrypt_color);
        $('.compose-body').css('border-color', encrypt_color);
        $('.compose-attachments').css('border-color', encrypt_color);
      },
      hide: function(event, api) {
        $('.select2-choices').css('border-color', '#CCCCCC');
        $('.compose-from').css('border-color', '#CCCCCC');
        $('.compose-subject input[type=text]').css('border-color', '#CCCCCC');

        $('.compose-options-crypto').css('border-color', '#CCCCCC');
        $('.compose-body').css('border-color', '#CCCCCC');
        $('.compose-attachments').css('border-color', '#CCCCCC');
      }
    }
  });
};


$(document).ready(function() {

  // Show Crypto Tooltips
  Mailpile.tooltip_compose_crypto_signature();
  Mailpile.tooltip_compose_crypto_encryption();


  $('.compose-choice-wrapper').qtip({
    content: {
      title: true,
      text: function(event, api) {
        var address = $(event.target).data('address');
        var contact_data = _.findWhere(Mailpile.instance.search_addresses, {address: address});
        return _.template($('#tooltip-contact-details').html(), contact_data);
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
      classes: 'qtip-thread-crypto'
    },
    position: {
      my: 'bottom center',
      at: 'top center',
			viewport: $(window),
			adjust: {
				x: -5,  y: 0
			}
    },
    show: {
      event: 'click',
      delay: 100
    },
    hide: {
      event: false,
      inactive: 800
    }
  });

});