/* Setup - Sources - Model */
var SourceModel = Backbone.Model.extend({
  url: '/setup/sources/',
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


/* Setup - Sources - View */
var SourcesView = Backbone.View.extend({
  initialize: function() {
    Backbone.Validation.bind(this);
		this.render();
  },
  render: function() {
    return this;
  },
  events: {
    "click #btn-setup-show-add-source"     : "showAddSource",
    "click #btn-setup-source-add-cancel"   : "cancelAddSource",
  	"click #btn-setup-source-settings"     : "showSourceSettings"
  },
  show: function() {
    this.$el.html(_.template($("#template-setup-sources").html()));
  },
  showAddSource: function(e) {
    e.preventDefault();
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    $('#setup').prepend($('#template-setup-source-settings').html());
  },
  cancelAddSource: function(e) {
    e.prevenDefault();
    $('#setup-box-source-settings').removeClass('bounceInLeft').addClass('bounceOutLeft');    
    //Backbone.history.navigate('#sources', true);
  },
  showSourceSettings: function() {
    this.$el.html(_.template($('#template-setup-source-local-settings').html(), SourceModel.attributes));
  }
});