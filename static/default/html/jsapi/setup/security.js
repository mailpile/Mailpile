/* Setup - Security - Model */
/* Commented out until supported
  'use_tor': true,
  'upload_keyservers': false,
  'email_key': false,
  'use_gravatar': false
*/
var SecurityModel = Backbone.Model.extend({
  defaults: {
    tinfoil: {
      'encrypt_events': true,
      'encrypt_index': true,
      'encrypt_mail': true,
      'encrypt_misc': true,
      'encrypt_vcards': true,
      'index_encrypted': true,
      'obfuscate_index': true,
      'gpg_email_key': false
    },
    paranoid: {
      'encrypt_events': true,
      'encrypt_index': true,
      'encrypt_mail': true,
      'encrypt_misc': true,
      'encrypt_vcards': true,
      'index_encrypted': false,
      'obfuscate_index': true,
      'gpg_email_key': true
    },
    above: {
      'encrypt_events': false,
      'encrypt_index': true,
      'encrypt_mail': true,
      'encrypt_misc': true,
      'encrypt_vcards': true,
      'index_encrypted': false,
      'obfuscate_index': true,
      'gpg_email_key': true
    },
    concerned: {
      'encrypt_events': false,
      'encrypt_index': true,
      'encrypt_mail': false,
      'encrypt_misc': true,
      'encrypt_vcards': true,
      'index_encrypted': false,
      'obfuscate_index': true,
      'gpg_email_key': true
    },
    normal: {
      'encrypt_events': false,
      'encrypt_index': true,
      'encrypt_mail': false,
      'encrypt_misc': false,
      'encrypt_vcards': false,
      'index_encrypted': false,
      'obfuscate_index': true,
      'gpg_email_key': true
    }
  }
});


/* Setup - Security - View */
var SecurityView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function() {
    return this;
  },
  events: {
    "click #btn-setup-security-save"         : "showPassphrase",
    "change #input-setup-security-level"     : "actionSecurityLevel",
    "submit #form-setup-security-passphrase" : "processSecurity",
    "click #btn-setup-security-passphrase"   : "processSecurity"
  },
  show: function() {
    Mailpile.API.setup_crypto_get({}, function(result) {

      // Generate UI friendly 'level' value
      var settings = _.values(result.result.prefs);
      settings[6] = true;
      settings = settings.join('-');
      level = 'custom';
      _.each(SecurityModel.attributes, function(state, name) {
        var check = _.values(state).join('-');
        if (settings == check) {
          level = name;
        }
      });

      var settings_data = _.extend({security_level: level}, result.result.prefs);
      var security_template = _.template($("#template-setup-security").html());
      $('#setup').html(security_template(settings_data));
    });
  },
  showPassphrase: function(e) {
    $('#modal-full').html($('#modal-security-enter-passphrase').html());
    $('#modal-full').modal(Mailpile.UI.ModalOptions);
    $('#input-setup-security-passphrase').focus();
  },
  actionSecurityLevel: function(e) {
    e.preventDefault();
    var level = $(e.target).val();

    // Show Some Snark
    if (level === 'crazy') {
      $('#modal-full').html($('#modal-security-level-idiot').html());
      $('#modal-full').modal(Mailpile.UI.ModalOptions);
      $(e.target).val('');
    }
    else if (_.indexOf(['tinfoil', 'paranoid', 'above', 'concerned', 'normal'], level) > -1) {
      _.each(SecurityModel.attributes[level], function(state, name) {
        $('#form-setup-security').find('input[name='+name+']').prop('checked', state).val(state);
      });
    }
    else if (level === 'custom') {
      console.log('custom settings');
    }
  },
  processSecurity: function(e) {
    e.preventDefault();
    var security_data = $('#form-setup-security').serializeObject();
    _.each($('#form-setup-security input:checkbox:not(:checked)'), function(val, key) {
      security_data[$(val).attr('name')] = false;
    });

    security_data['passphrase'] = $('#input-setup-security-passphrase').val();
    security_data['passphrase_confirm'] = $('#input-setup-security-passphrase').val();

    // Hide Form
    Mailpile.API.setup_crypto_post(security_data, function(result) {
      if (result.status === 'success') {
        $('#setup-security-passphrase-status').find('.validation-message').addClass('validation-success').html(result.message);
        setTimeout(function() {
          $('#modal-full').modal('hide');
        }, 1650);
      } else {
        $('#setup-security-passphrase-status').find('.validation-message').addClass('validation-error').html(result.message);
      }
    });
  }
});