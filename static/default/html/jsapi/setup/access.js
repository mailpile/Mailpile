/* Setup - Access - Model */
var AccessModel = Backbone.Model.extend({
  url: '/api/0//',
  validation: {
  }
});


/* Setup - Access - View */
var AccessView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){},
  events: {
    "click #btn-setup-advanced-access": "showAccess",
  },
  show: function() {
    this.$el.html(_.template($("#template-setup-access").html()));
  }
});