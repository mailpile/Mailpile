/* Profiles Model */
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


/* Profiles View */
var ProfilesView = Backbone.View.extend({
  initialize: function() {
    Backbone.Validation.bind(this);
		this.render();
  },
  render: function() {
  },
  events: {
  	"click #btn-setup-basic-info": "processBasic"
  },
  showProfiles: function() {
    this.$el.html(_.template($('#template-setup-profiles').html()));
  },
  processProfileAdd: function(e) {

    e.preventDefault();

    // Prepare Data
    var profile_data = $('#form-setup-basic-info').serializeObject();

    // Set Model & Validate
    this.model.set(profile_data);
    var validate = this.model.validate();

    // Process
    if (validate === undefined) {

      Backbone.history.navigate('#crypto-generated', true);
   }
    else {
      $.each(validate, function(elem, msg){
        $('#error-setup-' + elem).html(msg);
      });
    }
  }
});