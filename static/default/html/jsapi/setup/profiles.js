/* Setup - Profiles - Model */
var ProfilesModel = Backbone.Model.extend({
  url: '/setup/profiles/',
  validation: {
    name: {
      maxLength: 48,
      required: true,
      msg: 'Enter a name for your profile'
    },
    none: {
      maxLength: 48,
      required: false,
      msg: 'Enter a name for your profile'
    },
    email: {
      maxLength: 128,
      required: true,
      msg: 'Enter a valid email address'
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
    "click #btn-setup-cancel-add-profile" : "cancelAddProfile",
    "click #btn-setup-add-profile"        : "processAddProfile",
    "click .setup-profile-remove"         : "processRemoveProfile",
  	"click #btn-setup-basic-info"         : "processBasic"
  },
  show: function() {
    this.$el.html($('#template-setup-profiles').html());
  },
  showAddProfile: function() {
    $('#btn-setup-show-add-profile').hide();
    $('#form-setup-profile-add').fadeIn();
  },
  cancelAddProfile: function(e) {
    e.preventDefault();
    $('#btn-setup-show-add-profile').fadeIn();
    $('#form-setup-profile-add').hide();    
  },
  processAddProfile: function(e) {

    e.preventDefault();

    // Set Model & Validate
    var profile_data = $('#form-setup-profile-add').serializeObject();
    this.model.set(profile_data);
    var validate = this.model.validate();

    // Process
    if (validate === undefined) {
      console.log('inside validate yes');
      Mailpile.API.setup_profiles_post(profile_data, function(result) {
        console.log(result);
      });
    }
    else {
      $.each(validate, function(elem, msg){
        $('#error-setup-' + elem).html(msg);
      });
    }
  },
  processRemoveProfile: function(e) {

    e.preventDefault();
    var profile_id = $(e.target).data('profile_id');

    console.log(profile_id);

    Mailpile.API.profiles_remove_post({ rid: profile_id }, function(result) {
      console.log(result);

      $('#setup-profile-' + profile_id).fadeOut();

    });

  }
});