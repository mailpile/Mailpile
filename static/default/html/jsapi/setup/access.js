/* Setup - Access - Model */
var AccessModel = Backbone.Model.extend({
  validation: {}
});


/* Setup - Access - View */
var AccessView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  events: {
    "click #btn-setup-advanced-access": "showAccess",
  },
  show: function() {
    this.$el.html(_.template($("#template-setup-access").html()));
  }
});