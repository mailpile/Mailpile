/* Composer - Tooltips */

Mailpile.Composer.Tooltips.Signature = function() {
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


Mailpile.Composer.Tooltips.Encryption = function() {
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


Mailpile.Composer.Tooltips.ContactDetails = function() {
  $('.select2-search-choice').qtip({
    content: {
      title: true,
      text: function(e, api) {
        $target = $(e.target);
        var address = $target.data('address');

        if ($target.hasClass('select2-search-choice')) {
          address = $target.find('.compose-choice-name').data('address');
        }
        if ($target.hasClass('select2-search-choice-close')) {
          address = $target.parent().find('.compose-choice-name').data('address');
        }
        if ($target.is('img')) {
          address = $target.parent().parent().find('.compose-choice-name').data('address');
        } 

        var contact_data = _.findWhere(Mailpile.instance.addresses, { address: address });
        if (contact_data) {

          if (contact_data.photo === undefined) {
            contact_data.photo = '';
          }

          var contact_template = _.template($('#tooltip-contact-details').html());
          return contact_template(contact_data);
        }
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
      classes: 'qtip-contact-details'
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
      delay: 50
    },
    hide: {
      event: true,
      inactive: 750
    }
  });
};

Mailpile.Composer.Tooltips.AttachKey = function() {
  $('.compose-attach-key').qtip({
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
      delay: 50
    },
    hide: {
      event: true,
      inactive: 750
    }
  });
};