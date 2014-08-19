/* Setup - Profiles - Model */
var ProfileModel = Backbone.Model.extend({
  defaults: {
    id: 'new',
    action: '{{_("Add")}}',
    warning: 'none',
    name: '',
    email: '',
    pass: '',
    note: '',
    route_id: ''
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
    route_id: {
      minLength: 1,
      required: true,
      msg: 'Create & select a sending route'
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

      // Hide Delete (if only 1 profile)
      if (ProfilesCollection.length === 1) {
        $('.setup-profile-remove').parent().hide();
      }
    });

    return this;
  },
  processRemove: function(e) {
    e.preventDefault();
    var profile_id = $(e.target).data('id');
    Mailpile.API.profiles_remove_post({ rid: profile_id }, function(result) {
      $('#setup-profile-' + profile_id).fadeOut();
    });
  }
});