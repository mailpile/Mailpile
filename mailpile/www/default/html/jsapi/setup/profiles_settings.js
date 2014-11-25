/* Setup - Profiles - View */
var ProfilesSettingsView = Backbone.View.extend({
  initialize: function() {
    Backbone.Validation.bind(this);
		this.render();
  },
  render: function() {
    return this;
  },
  events: {
    "keyup #input-setup-profile-email"    : "actionCheckEmailMagic",
    "blur #input-setup-profile-pass"      : "actionCheckAuth",
    "mouseover #btn-setup-profile-save"   : "actionCheckAuth",
    "click #btn-setup-connection-check"   : "actionCheckAuth",
    "change #input-setup-profile-route_id": "actionHandleRoute",
    "click .btn-setup-profile-edit-route" : "actionEditRoute",
    "click #btn-setup-profile-add"        : "processSettingsAdd",
    "click #btn-setup-profile-edit"       : "processSettingsEdit"
  },
  show: function() {
    var new_model = this.model.defaults;
    Mailpile.API.setup_profiles_get({}, function(result) {
      var add_data = _.extend(new_model, {routes: result.result.routes, provider: ''});
      var profile_template = _.template($('#template-setup-profiles-add').html());
      $('#setup').html(profile_template(add_data));
      TooltipsView.showHelp();
    });
  },
  showEdit: function(id) {
    $('#setup-profiles-list').removeClass('bounceInUp').addClass('bounceOutUp');

    // Load Data & Add to Collection
    Mailpile.API.setup_profiles_get({}, function(result) {
      var profile = result.result.profiles[id];
      if (profile !== undefined) {

        // Prep Data
        var provider = SetupMagic.providers[profile.email.replace(/.*@/, "")];
        _.extend(profile, { id: id, action: 'Edit', action_i18n: '{{_("Edit")}}', provider: provider });
        var edit_data = _.extend(profile, {routes: result.result.routes});

        // Render
        var profile_template = _.template($('#template-setup-profiles-add').html());
        $('#setup').html(profile_template(edit_data));
        TooltipsView.showHelp();

        // Show Validation Feedback
        ProfilesSettingsView.model.set(edit_data);
        ProfilesSettingsView.model.validate();
      }
    });
  },
  showGmailWarning: function(message) {

    if (this.model.attributes.warning !== 'used' || message !== 'warning') {
      this.model.set({warning: 'used'});

      // Load Content
      $('#modal-full').html($('#modal-gmail-auth-' + message).html());
  
      // Instantiate
      $('#modal-full').modal(Mailpile.UI.ModalOptions);

      // Empty Password & Add Testing Link
      setTimeout(function() {
        $('#input-setup-profile-pass').val('');
        $('#validation-pass').find('.check-auth')
          .removeClass('color-08-green color-12-red')
          .html('<a href="#" id="btn-setup-connection-check" class="setup-check-connection"><span class="icon-help"></span> {{_("Test Connection")}}</a>');
      }, 1000);
    }
  },
  actionCheckEmailMagic: function(e) {

    var domain = $(e.target).val().replace(/.*@/, "");
    var provider = SetupMagic.providers[domain];

    if (provider && this.model.attributes.warning !== 'used') {
      $('#input-setup-profile-pass').data('provider', provider).attr('data-provider', provider);
      $('#validation-pass').fadeIn('fast', function(){
        $('#input-setup-profile-pass').attr("tabindex", -1).focus();
      });

      // Show Gmail Warning
      if (provider === 'gmail') {
        ProfilesSettingsView.showGmailWarning('warning');
      }
    }
  },
  actionCheckAuth: function(e) {

    // Prevent from incorrectly firing
    if ($('#input-setup-profile-email').val() && $('#input-setup-profile-pass').val() && SetupMagic.status == 'error') {

      // Disable Save Button
      $('#btn-setup-profile-save').attr("disabled", true);

      // Status UI Message
      $('#validation-pass').find('.check-auth')
        .removeClass('color-12-red color-08-green')
        .html('<em>{{_("Testing Credentials")}}</em> <img src="/static/css/select2-spinner.gif">');

      var provider = $('#input-setup-profile-pass').data('provider');
      var presets = SetupMagic.presets[provider];
      var sending_data = _.extend(presets.sending, {
        username: $('#input-setup-profile-email').val(),
        password: $('#input-setup-profile-pass').val()
      });

      Mailpile.API.setup_test_route_post(sending_data, function(result) {

        // Renable Save Profile
        $('#btn-setup-profile-save').removeAttr('disabled');

        // Yay, Add Magic & Success
        SetupMagic.status = result.status;
        if (result.status ==  'success') {
          $('#validation-pass').find('.check-auth')
            .removeClass('color-12-red')
            .addClass('color-08-green')
            .html('<span class="icon-checkmark"></span> {{_("Successfully Connected")}}');

          // Add Sending
          SetupMagic.provider = provider;
          sending_data['_section'] = 'routes.' + SetupMagic.random_id;

          Mailpile.API.settings_set_post(sending_data, function(result) {
            $('#input-setup-profile-route_id').prepend('<option value="' + SetupMagic.random_id + '">' + sending_data.name + '</option>').val(SetupMagic.random_id);
            $('#validation-route').fadeIn();
          });
        }
        else if (result.status == 'error') {
          $('#validation-pass').find('.check-auth')
            .removeClass('color-08-green')
            .addClass('color-12-red')
            .html('<span class="icon-x"></span> {{_("Error Connecting")}}: '
                  + result.error.error);

          if (provider == 'gmail') {
            ProfilesSettingsView.showGmailWarning('error');
          }
        }
      });
    }
  },
  actionHandleRoute: function(e) {

    e.preventDefault();
    var route_id = $('#input-setup-profile-route_id').val();

    // Show Add Route Form
    if (route_id == 'new') {

      // Update Profile Model
      ProfilesSettingsView.model.set({
        name: $('#input-setup-profile-name').val(),
        email: $('#input-setup-profile-email').val(),
        pass: $('#input-setup-profile-pass').val(),
        note: $('#input-setup-profile-note').val()
      });

      // Prep Route Model
      var domain = $('#input-setup-profile-email').val().replace(/.*@/, "");
      SendingView.model.set({
        id: Math.random().toString(36).substring(2),
        complete: 'profiles',
        name: $('#input-setup-profile-name').val() + ' {{_("Route")}}',
        username: $('#input-setup-profile-email').val(),
        password: $('#input-setup-profile-pass').val(),
        host: 'smtp.' + domain
      });

      // Show Sending Form
      $('#form-setup-profile-settings').hide();
      $('#setup-profiles-route-editing').removeClass('hide').find('span.name').html($('#input-setup-profile-name').val());
      var sending_template = _.template($("#template-setup-sending-settings").html());
      $('#setup-profiles-route-settings').html(sending_template(SendingView.model.attributes)).removeClass('hide');

    } else if (route_id === '') {
      $('#input-setup-profile-route_id').removeClass('half-bottom');
      $('#setup-profile-edit-route').addClass('hide');
    }
  },
  actionEditRoute: function(e) {
    e.preventDefault();
    var route_id = $('#input-setup-profile-route_id').find('option:selected').val();
    Backbone.history.navigate('#sending/'+route_id, true);
  },
  actionRouteAdded: function(route_id, route_name) {

    // Hide Sending Form
    $('#setup-sending-settings').removeClass('bounceInBottom').addClass('bounceOutDown');

    setTimeout(function() {
      $('#setup-profiles-route-editing').addClass('hide');
      $('#setup-profiles-route-settings').addClass('hide');
    }, 400);

    // Show Profile Again
    setTimeout(function() {
      $('#form-setup-profile-settings').fadeIn();
      $('#input-setup-profile-route_id').prepend('<option value="' + route_id + '">' + route_name + '</option>').val(route_id);
    }, 550);

    this.model.set({ route_id: route_id });
    this.model.validate();

  },
  processSettingsAdd: function(e) {

    e.preventDefault();

    // Update Model
    var profile_data = $('#form-setup-profile-settings').serializeObject();
    this.model.set(profile_data);

    // Validate & Process
    if (!this.model.validate()) {
      Mailpile.API.setup_profiles_post(profile_data, function(result) {

        // Reset Model & Navigate
        StateModel.fetch({
          success: function(model) {
            ProfilesSettingsView.model.set(ProfilesSettingsView.model.defaults);
            Backbone.history.navigate('#profiles', true);
          }
        });

        // Add Setup Magic (Source)
        if (SetupMagic.status == 'success') {
          SetupMagic.processAdd({
            username: profile_data.email,
            password: profile_data.pass
          });
        }
      });
    }
  },
  processSettingsEdit: function(e) {

    e.preventDefault();
    var profile_data = $('#form-setup-profile-settings').serializeObject();
    this.model.set(profile_data);

    // Validate & Process
    if (!this.model.validate()) {

      var profile_id = $('#input-setup-profile-id').val();

      // Loop through elements
      _.each($('.profile-update'), function(item, key) {
        if ($(item).val() !== '') {
          var vcard_data = {
            rid: profile_id,
            name: $(item).data('vcard_name'),
            value: $(item).val(),
            replace_all: true
          };
  
          // Update VCard
          Mailpile.API.vcards_addlines_post(vcard_data, function(result) {});
        }
      });

      // Update Model
      ProfilesSettingsView.model.set(ProfilesSettingsView.model.defaults);

      // Update State
      StateModel.fetch({
        success: function(model) {
          Backbone.history.navigate('#profiles', true);
        }
      });
    }
  }
});
