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
    "click #btn-setup-passphrase": "processPassphrase"
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
          $('#identity-vault-lock')
            .find('.icon-lock-closed')
            .removeClass('icon-lock-closed')
            .addClass('icon-lock-open color-08-green bounce');

          if (result.result.creating_key) {
            $('#setup-passphrase-creating').fadeIn().removeClass('hide');
          } else {
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