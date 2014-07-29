/* Setup - Security - Model */
var SecurityModel = Backbone.Model.extend({
  url: '/api/0//',
  validation: {
  }
});


/* Setup - Security - View */
var SecurityView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){},
  events: {
    "click #btn-setup-advanced-access": "showAccess",
  },
  show: function() {
    this.$el.html(_.template($("#template-setup-security").html()));
  }
});