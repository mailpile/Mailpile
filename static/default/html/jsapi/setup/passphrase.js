/* Passphrase Model */
var PassphraseModel = Backbone.Model.extend({
  validation: {
    passphrase: {
      minLength: 5,
      required: true,
      msg: 'Enter a passphrase of at least 10 letters'
    },
    passphrase_confirm: {
      minLength: 5,
      required: true,
      equalTo: 'passphrase',
      msg: 'Your confirmation passphrase does not match'
    },
    choose_key: {
      required: false
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
    this.$el.html($('#template-setup-passphrase').html());
//  this.stickit();
    return this;
  },
  events: {
    "click #btn-setup-passphrase": "processPassphrase"
  },
/*
  bindings: {
    '#input-setup-passphrase': 'passphrase',
    '#input-setup-passphrase-confirm': 'passphrase_confirm'
  },
*/
  showPassphrase: function() {
    $('#setup-progress').find('')
  },
  processPassphrase: function(e) {

    e.preventDefault();

    // Set Model & Validate
    var passphrase_data = $('#form-setup-passphrase').serializeObject();
    this.model.set(passphrase_data);
    var validate = this.model.validate();

    // Process
    if (validate === undefined) {
      Mailpile.API.setup_crypto(passphrase_data, function(result) {
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
          $('#identity-vault-lock').find('.icon-lock-closed').addClass('color-12-red bounce');
          Mailpile.notification(result.status, result.message);
          setTimeout(function() {
            $('#identity-vault-lock').find('.icon-lock-closed').removeClass('color-12-red bounce');
          }, 2500);
        }
      });
   }
    else {
      $.each(validate, function(elem, msg){
        $('#error-setup-' + elem).html(msg);
      });
    }
  }
});