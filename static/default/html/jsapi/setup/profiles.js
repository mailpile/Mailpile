/* Setup - Profiles - Model */
var ProfileModel = Backbone.Model.extend({
  url: '/api/0/profiles_add/',
  validation: {
    name: {
      required: true,
      msg: 'Enter a name for your profile'
    },
    email: {
      pattner: 'email',
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
  },
  events: {
    "click #btn-setup-show-add-profile"   : "showAddProfile",
    "click #btn-setup-cancel-add-profile" : "cancelAddProfile",
    "click #btn-setup-add-profile"        : "processAddProfile",
    "click .setup-profile-remove"         : "processRemoveProfile",
  	"click #btn-setup-basic-info"         : "processBasic"
  },
  showProfiles: function() {

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
    this.model.set($('#form-setup-profile-add').serializeObject());
    var validate = this.model.validate();

    // Process
    if (validate === undefined) {

      var add_profile = this.model.sync();
      console.log(add_profile);

    }
    else {
      $.each(validate, function(elem, msg){
        $('#error-setup-' + elem).html(msg);
      });
    }
  },
  processRemoveProfile: function() {

    alert('this will remove a profile');
    var profile_id = ;
    
    Mailpile.API.profiles_remove({ rid: profile_id }, function(result) {
      console.log(result);

    });

  }
});