$(document).ready(function() {

  // Show Crypto Tooltips
  $('.compose-crypto-signature').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var html = '<div>\
          <h4 class="' + $(this).data('crypto_color') + '">' + $(this).html() + '</h4>\
          <p>' + $(this).attr('title') + '</p>\
          </div>';
        return html;
      }
    },  
    style: {
     tip: {
        corner: 'right center',
        mimic: 'right center',
        border: 0,
        width: 10,
        height: 10
      },
      classes: 'qtip-thread-crypto'
    },
    position: {
      my: 'right center',
      at: 'left center',
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
      }
    }
  });


  $('.compose-crypto-encryption').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var html = '<div>\
          <h4 class="' + $(this).data('crypto_color') + '">' + $(this).html() + '</h4>\
          <p>' + $(this).attr('title') + '</p>\
          </div>';
        return html;
      }
    },
    style: {
     tip: {
        corner: 'right center',
        mimic: 'right center',
        border: 0,
        width: 10,
        height: 10
      },
      classes: 'qtip-thread-crypto'
    },
    position: {
      my: 'right center',
      at: 'left center',
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

        $('.compose-body').css('border-color', encrypt_color);
        $('.compose-attachments').css('border-color', encrypt_color);
      },
      hide: function(event, api) {

        $('.select2-choices').css('border-color', '#CCCCCC');
        $('.compose-from').css('border-color', '#CCCCCC');
        $('.compose-subject input[type=text]').css('border-color', '#CCCCCC');

        $('.compose-body').css('border-color', '#CCCCCC');
        $('.compose-attachments').css('border-color', '#CCCCCC');
      }
    }
  });


  $('.select2-search-choice').qtip({
    content: {
      title: true,
      text: function(event, api) {
        var contact_html = $(event.target).html();
        var html = 'Hiyo party people :P'
        return contact_html;
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
      delay: 150
    },
    hide: {
      event: false,
      inactive: 800
    },
    events: {
      show: function(event, api) {
        
      },
      hide: function(event, api) {
        
      }
    }
  });

});