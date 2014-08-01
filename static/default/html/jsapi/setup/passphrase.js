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
    return this;
  },
  events: {
    "click #btn-setup-passphrase": "processPassphrase"
  },
  show: function() {
    $('#setup-progress').find('')
    this.$el.html($('#template-setup-passphrase').html());
  },
  processPassphrase: function(e) {

    e.preventDefault();

    // Has Keychain (set passprhase_confirm)
    if ($('#input-setup-passphrase_confirm').attr('type') == 'hidden') {
      $('#input-setup-passphrase_confirm').val($('#input-setup-passphrase').val());
    }

    // Prep & Validate Data
    var passphrase_data = $('#form-setup-passphrase').serializeObject();
    this.model.set(passphrase_data);

    // Process Form
    if (!this.model.validate()) {
      $('#form-setup-passphrase').hide();
      

      Mailpile.API.setup_crypto_post(passphrase_data, function(result) {
        if (result.status == 'success') {
          $('#identity-vault-lock')
            .find('.icon-lock-closed')
            .removeClass('icon-lock-closed')
            .addClass('icon-lock-open color-08-green bounce');
          setTimeout(function() {
            Backbone.history.navigate('#profiles', true);
          }, 2500);
        }
        else if (result.status == 'error' && result.error.invalid_passphrase) {

          $('#form-setup-passphrase').show();


          $('#identity-vault-lock').find('.icon-lock-closed').addClass('color-12-red bounce');
          Mailpile.notification(result.status, result.message);
          setTimeout(function() {
            $('#identity-vault-lock').find('.icon-lock-closed').removeClass('color-12-red bounce');
          }, 2500);
        }
      });
    }
  }
});