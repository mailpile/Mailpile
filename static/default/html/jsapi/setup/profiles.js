/* Setup - Profiles - Model */
var ProfileModel = Backbone.Model.extend({
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
    "click #btn-setup-show-add-profile": "showAddProfile",
    "click #btn-setup-hide-add-profile": "hideAddProfile",
    "click .setup-profile-remove": "removeProfile",
  	"click #btn-setup-basic-info": "processBasic"
  },
  showProfiles: function() {

    this.$el.html($('#template-setup-profiles').html());
  },
  showAddProfile: function() {
    $('#btn-setup-show-add-profile').hide();
    $('#form-setup-profile-add').fadeIn();
  },
  hideAddProfile: function(e) {
    e.preventDefault();
    $('#btn-setup-show-add-profile').fadeIn();
    $('#form-setup-profile-add').hide();    
  },
  processProfileAdd: function(e) {

    e.preventDefault();

    // Set Model & Validate
    this.model.set($('#form-setup-profile-add').serializeObject());
    var validate = this.model.validate();

    // Process
    if (validate === undefined) {

      Mailpile.API.profiles_remove({ key: value}, function() {

      });

      // Backbone.history.navigate('#crypto-generated', true);
   }
    else {
      $.each(validate, function(elem, msg){
        $('#error-setup-' + elem).html(msg);
      });
    }
  },
  removeProfile: function() {

    
    alert('this will remove a profile');
  }
});