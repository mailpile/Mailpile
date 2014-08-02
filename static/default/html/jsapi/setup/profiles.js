/* Setup - Profiles - Model */
var ProfilesModel = Backbone.Model.extend({
  url: '/setup/profiles/',
  validation: {
    name: {
      minLength: 1,
      maxLength: 48,
      required: true,
      msg: 'Enter a name for your profile'
    },
    note: {
      maxLength: 48,
      required: false
    },
    email: {
      maxLength: 128,
      pattern: 'email',
      required: true,
      msg: 'Enter a valid email address'
    },
    password: {
      required: false
    }
  }
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
    "click #btn-setup-show-add-profile"   : "showAddProfile",
    "click #btn-setup-add-profile"        : "processAddProfile",
    "click .setup-profile-remove"         : "processRemoveProfile"
  },
  show: function() {
    this.$el.html($('#template-setup-profiles').html());
  },
  showAddProfile: function() {
    $('#setup-profiles-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    this.$el.html(_.template($('#template-setup-profiles-add').html()));
  },
  processAddProfile: function(e) {

    e.preventDefault();

    // Update Model
    var profile_data = $('#form-setup-profile-add').serializeObject();
    this.model.set(profile_data);

    // Validate & Process
    if (!this.model.validate()) {
      Mailpile.API.setup_profiles_post(profile_data, function(result) {
        console.log(result);
      });
    }
  },
  processRemoveProfile: function(e) {

    e.preventDefault();
    var profile_id = $(e.target).data('profile_id');

    Mailpile.API.profiles_remove_post({ rid: profile_id }, function(result) {
      $('#setup-profile-' + profile_id).fadeOut();
    });
  }
});