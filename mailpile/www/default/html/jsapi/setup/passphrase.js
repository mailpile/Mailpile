/* Passphrase Model */
var PassphraseModel = Backbone.Model.extend({
  validation: {
    passphrase: {
      required: true,
      msg: 'Enter a passphrase of at least 10 letters'
    },
    passphrase_confirm: {
      required: true,
      equalTo: 'passphrase',
      msg: 'Your confirmation passphrase does not match'
    },
    choose_key: {
      required: false,
      msg: 'You must select'
    }
  }
});


/* Passphrase View */
var PassphraseView = Backbone.View.extend({
  initialize: function() {
    Backbone.Validation.bind(this);
		this.render();
  },
  render: function() {
    if ($('#setup-passphrase-keys-exists').length) {
      $('#setup-passphrase-existing-confirm').addClass('hide');
    }
    return this;
  },
  events: {
    "click .setup-crypto-more-uid" : "showMoreUID",
    "click .setup-crypto-fingerprint-learn": "showFingerprintLearn",
    "click #btn-setup-passphrase"  : "processPassphrase"
  },
  showMoreUID: function(e) {
    e.preventDefault();
    $(e.target).hide();
    $('.setup-crypto-uid-more').fadeIn();
  },
  showFingerprintLearn: function(e) {
    e.preventDefault();
    alert('Use this to help other people verify your encryption key by reading it to them in person, phone, or video chat, and have them compare it to the fingerprint on the encryption key they have!');
  },
  processPassphrase: function(e) {

    e.preventDefault();

    // Has Keychain (set passprhase_confirm)
    if ($('#setup-passphrase-keys-exists').length) {
      $('#input-setup-passphrase_confirm').val($('#input-setup-passphrase').val());
    }

    // Update Model
    var passphrase_data = $('#form-setup-passphrase').serializeObject();
    this.model.set(passphrase_data);

    // Validate & Process
    if (!this.model.validate()) {

      // Hide Form
      $('#form-setup-passphrase').hide();

      Mailpile.API.setup_crypto_post(passphrase_data, function(result) {
        if (result.status == 'success') {
          if (result.result.creating_key) {
            $('#identity-vault-lock')
              .find('.icon-lock-closed')
              .removeClass('icon-lock-closed')
              .addClass('icon-key color-08-green bounce');
            $('#setup-passphrase-creating').fadeIn().removeClass('hide');
          } else {
            $('#identity-vault-lock')
              .find('.icon-lock-closed')
              .removeClass('icon-lock-closed')
              .addClass('icon-lock-open color-08-green bounce');
            $('#setup-crypto-chosen_key').html(Mailpile.nice_fingerprint(result.result.chosen_key));
            $('#setup-passphrase-authenticated').fadeIn();
          }
        }
        else if (result.status == 'error' && result.error.invalid_passphrase) {

          // Show Form
          $('#form-setup-passphrase').show();

          // Error UI feedback
          $('#identity-vault-lock').find('.icon-lock-closed').addClass('color-12-red bounce');

          alert(result.message);
          setTimeout(function() {
            $('#identity-vault-lock').find('.icon-lock-closed').removeClass('color-12-red bounce');
          }, 2500);
        }
      });
    }
  }
});