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
      'obfuscate_index': true
    },
    paranoid: {
      'encrypt_events': true,
      'encrypt_index': true,
      'encrypt_mail': true,
      'encrypt_misc': true,
      'encrypt_vcards': true,
      'index_encrypted': false,
      'obfuscate_index': true
    },
    above: {
      'encrypt_events': false,
      'encrypt_index': true,
      'encrypt_mail': true,
      'encrypt_misc': true,
      'encrypt_vcards': true,
      'index_encrypted': false,
      'obfuscate_index': true
    },
    concerned: {
      'encrypt_events': false,
      'encrypt_index': true,
      'encrypt_mail': false,
      'encrypt_misc': true,
      'encrypt_vcards': true,
      'index_encrypted': false,
      'obfuscate_index': true
    },
    normal: {
      'encrypt_events': false,
      'encrypt_index': false,
      'encrypt_mail': false,
      'encrypt_misc': false,
      'encrypt_vcards': false,
      'index_encrypted': false,
      'obfuscate_index': true
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
    "click #btn-setup-advanced-access"   : "showAccess",
    "change #input-setup-security-level" : "actionSecurityLevel",
    "click #btn-setup-security-save"     : "processSecurity",
  },
  show: function() {
    Mailpile.API.setup_crypto_get({}, function(result) {

      // Generate UI friendly 'level' value
      var settings = _.values(result.result.prefs);
      settings[6] = true;
      settings = settings.join('-');
      level = '';
      _.each(SecurityModel.attributes, function(state, name) {
        var check = _.values(state).join('-');
        if (settings == check) {
          level = name;
        }
      });

      var settings_data = _.extend({security_level: level}, result.result.prefs);
      $('#setup').html(_.template($("#template-setup-security").html(), settings_data));
    });
  },
  actionSecurityLevel: function(e) {
    e.preventDefault();
    var level = $(e.target).val();

    // Show Some Snark
    if (level === 'crazy') {
      $('#modal-full').html($('#modal-security-level-idiot').html());
      $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
      $(e.target).val('');
    }
    else if (_.indexOf(['tinfoil', 'paranoid', 'above', 'concerned', 'normal'], level) > -1) {
      _.each(SecurityModel.attributes[level], function(state, name) {
        $('#form-setup-security').find('input[name='+name+']').prop('checked', state).val(state);
      });
    }
  },
  processSecurity: function(e) {

    e.preventDefault();

    var security_data = $('#form-setup-security').serializeObject();

    _.each($('#form-setup-security input:checkbox:not(:checked)'), function(val, key) {
      security_data[$(val).attr('name')] = false;
    });

    // Hide Form
    Mailpile.API.setup_crypto_post(security_data, function(result) {

      console.log(result);

    });
  }
});