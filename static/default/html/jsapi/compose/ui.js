/* Compose - Render crypto "signature" of a message */
Mailpile.compose_render_signature = function(status) {
    if (status === 'sign') {
        $('.compose-crypto-signature').data('crypto_color', 'crypto-color-green');  
        $('.compose-crypto-signature').attr('title', $('.compose-crypto-signature').data('crypto_title_signed'));
        $('.compose-crypto-signature span.icon').removeClass('icon-signature-none').addClass('icon-signature-verified');
        $('.compose-crypto-signature span.text').html($('.compose-crypto-signature').data('crypto_signed'));
        $('.compose-crypto-signature').removeClass('none').addClass('signed bounce');

    } else if (status === 'none') {
        $('.compose-crypto-signature').data('crypto_color', 'crypto-color-gray');  
        $('.compose-crypto-signature').attr('title', $('.compose-crypto-signature').data('crypto_title_not_signed'));
        $('.compose-crypto-signature span.icon').removeClass('icon-signature-verified').addClass('icon-signature-none');
        $('.compose-crypto-signature span.text').html($('.compose-crypto-signature').data('crypto_not_signed'));
        $('.compose-crypto-signature').removeClass('signed').addClass('none bounce');

    } else {
        $('.compose-crypto-signature').data('crypto_color', 'crypto-color-red');
        $('.compose-crypto-signature').attr('title', $('.compose-crypto-signature').data('crypto_title_signed_error'));
        $('.compose-crypto-signature span.icon').removeClass('icon-signature-none icon-signature-verified').addClass('icon-signature-error');
        $('.compose-crypto-signature span.text').html($('.compose-crypto-signature').data('crypto_signed_error'));
        $('.compose-crypto-signature').removeClass('none').addClass('error bounce');
    }

      // Set Form Value
    if ($('#compose-signature').val() !== status) {

        $('.compose-crypto-signature').addClass('bounce');
        $('#compose-signature').val(status);

        // Remove Animation
        setTimeout(function() {
          $('.compose-crypto-signature').removeClass('bounce');
        }, 1000);

        this.compose_set_crypto_state();
    }
};


/* Compose - Render crypto "encryption" of a message */
Mailpile.compose_render_encryption = function(status) {
    console.log("Status: le " + status);
    if (status == 'encrypt') {
        $('.compose-crypto-encryption').data('crypto_color', 'crypto-color-green');
        $('.compose-crypto-encryption').attr('title', $('.compose-crypto-encryption').data('crypto_title_encrypt'));
        $('.compose-crypto-encryption span.icon').removeClass('icon-lock-open').addClass('icon-lock-closed');
        $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_encrypt'));
        $('.compose-crypto-encryption').removeClass('none error cannot').addClass('encrypted');

    } else if (status === 'cannot') {
        $('.compose-crypto-encryption').data('crypto_color', 'crypto-color-orange');
        $('.compose-crypto-encryption').attr('title', $('.compose-crypto-encryption').data('crypto_title_cannot_encrypt'));
        $('.compose-crypto-encryption span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
        $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_cannot_encrypt'));
        $('.compose-crypto-encryption').removeClass('none encrypted error').addClass('cannot');

    } else if (status === 'none' || status == '') {
        $('.compose-crypto-encryption').data('crypto_color', 'crypto-color-gray');
        $('.compose-crypto-encryption').attr('title', $('.compose-crypto-encryption').data('crypto_title_none'));
        $('.compose-crypto-encryption span.icon').removeClass('icon-lock-closed').addClass('icon-lock-open');
        $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_none'));
        $('.compose-crypto-encryption').removeClass('encrypted cannot error').addClass('none');

    } else {
        $('.compose-crypto-encryption').data('crypto_color', 'crypto-color-red');
        $('.compose-crypto-encryption').attr('title', $('.compose-crypto-encryption').data('crypto_title_encrypt_error'));
        $('.compose-crypto-encryption span.icon').removeClass('icon-lock-open icon-lock-closed').addClass('icon-lock-error');
        $('.compose-crypto-encryption span.text').html($('.compose-crypto-encryption').data('crypto_cannot_encrypt'));
        $('.compose-crypto-encryption').removeClass('encrypted cannot none').addClass('error');
    }

    // Set Form Value
    if ($('#compose-encryption').val() !== status) {

        $('.compose-crypto-encryption').addClass('bounce');
        $('#compose-encryption').val(status);

        // Remove Animation
        setTimeout(function() {
          $('.compose-crypto-encryption').removeClass('bounce');
        }, 1000);
        
        this.compose_set_crypto_state();
    }
};


/* Compose - Render adding new message to thread */
Mailpile.compose_render_message_thread = function(mid) {
  window.location.href = Mailpile.urls.message_sent + mid + "/";
  // FIXME: make this ajaxy and nice transitions and such
  // $('#form-compose-' + mid).slideUp().remove();
};