/* Setup - Profiles - Model */
var ProfileModel = Backbone.Model.extend({
  defaults: {
    id: 'new',
    action: 'Add',
    name: '',
    email: '',
    pass: '',
    note: ''
  },
  validation: {
    name: {
      minLength: 1,
      maxLength: 48,
      required: true,
      msg: 'Enter a name for your profile'
    },
    email: {
      maxLength: 128,
      pattern: 'email',
      required: true,
      msg: 'Enter a valid email address'
    },
    pass: {
      minLength: 1,
      required: false
    },
    note: {
      maxLength: 48,
      required: false
    },
    auto_configurable: false,
    pgp_keys: []
  }
});


var ProfilesCollection = Backbone.Collection.extend({
  url: '/setup/profiles/as.json',
  model: ProfileModel
});


/* Setup - Profiles - View */
var ProfilesView = Backbone.View.extend({
  initialize: function() {
    Backbone.Validation.bind(this);
		this.render();
  },
  render: function() {
    return this;
  },
  events: {
    "click #btn-setup-show-add-profile"   : "showAdd",
    "blur #input-setup-profile-email"     : "actionCheckEmailMagic",
    "blur #input-setup-profile-pass"      : "actionCheckAuth",
    "mouseover #btn-setup-profile-save"   : "actionCheckAuth",
    "click #btn-setup-profile-save"       : "processSettings",
    "click .setup-profile-remove"         : "processRemove"
  },
  show: function() {

    this.$el.html($('#template-setup-profiles').html());

    // Load Data & Add to Collection
    Mailpile.API.setup_profiles_get({}, function(result) {

      if (_.isEmpty(result.result.profiles)) {
        Backbone.history.navigate('#profiles/add', true);
      }

      _.each(result.result.profiles, function(val, key) {
        var profile = new ProfileModel(_.extend({id: key, action: 'Edit'}, val));
        ProfilesCollection.add(profile);
        $('#setup-profiles-list-items').append(_.template($('#template-setup-profiles-item').html(), profile.attributes));
      });

    });

    return this;
  },
  showAdd: function() {
    $('#setup-profiles-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    this.$el.html(_.template($('#template-setup-profiles-add').html(), this.model.attributes));
  },
  showEdit: function(id) {
    $('#setup-profiles-list').removeClass('bounceInUp').addClass('bounceOutLeft');

    // Load Data & Add to Collection
    Mailpile.API.setup_profiles_get({}, function(result) {
      var profile = result.result.profiles[id];
      if (profile !== undefined) {
        profile = _.extend({ id: id, action: 'Edit' }, profile);
        $('#setup').html(_.template($('#template-setup-profiles-add').html(), profile));
      }
    });
  },
  actionCheckEmailMagic: function(e) {
    var domain = $(e.target).val().replace(/.*@/, "");
    var provider = SetupMagic.providers[domain];
    if (provider) {
      $('#input-setup-profile-pass').data('provider', provider).attr('data-provider', provider);
      $('#validation-pass').fadeIn(function(){
        $('#input-setup-profile-pass').attr("tabindex", -1).focus();
      });
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
            .html('{{_("Successfully Connected")}} <span class="icon-checkmark"></span>');
          SetupMagic.provider = provider;
        }
        else if (result.status == 'error') {
          $('#validation-pass').find('.check-auth')
            .removeClass('color-08-green')
            .addClass('color-12-red')
            .html('{{_("Error Connecting")}} <span class="icon-x"></span>');
        }
      });
    }
  },
  processSettings: function(e) {

    e.preventDefault();
    if ($(e.target).data('id') == 'new') {

      // Update Model
      var profile_data = $('#form-setup-profile-settings').serializeObject();
      this.model.set(profile_data);
  
      // Validate & Process
      if (!this.model.validate()) {
        Mailpile.API.setup_profiles_post(profile_data, function(result) {

          // Add Setup Magic
          if (SetupMagic.status == 'success') {
            SetupMagic.processAdd({
              username: $('#input-setup-profile-email').val(),
              password: $('#input-setup-profile-pass').val()
            });
          }

          // Reset Model & Navigate
          ProfilesView.model.set({name: '', email: '', pass: '', note: ''});

          Backbone.history.navigate('#profiles', true);
        });
      }
    } else {
      alert('We do not support editing profiles yet, sorry!');
    }
  },
  processRemove: function(e) {

    e.preventDefault();
    var profile_id = $(e.target).data('id');

    Mailpile.API.profiles_remove_post({ rid: profile_id }, function(result) {
      $('#setup-profile-' + profile_id).fadeOut();
    });
  }
});