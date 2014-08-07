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
    var profile = ProfilesCollection.get(id);
    if (profile !== undefined) {
      this.$el.html(_.template($('#template-setup-profiles-add').html(), profile.attributes));
    } else {
      Backbone.history.navigate('#profiles', true);
    }
  },
  actionCheckEmailMagic: function(e) {
    var domain = $(e.target).val().replace(/.*@/, "");
    var check = SetupMagic.providers[domain];
    if (check) {
      $('#validation-pass').fadeIn();
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
          if (result.status == 'success') {
            // Reset Model & Navigate
            ProfilesView.model.set({name: '', email: '', pass: '', note: ''});
            Backbone.history.navigate('#profiles', true);
          }
          else {
            alert('Error saving Profile');
          }
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