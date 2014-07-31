/* Setup - Security - Model */
var SecurityModel = Backbone.Model.extend({
  validation: {}
});


/* Setup - Security - View */
var SecurityView = Backbone.View.extend({
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
    this.$el.html(_.template($("#template-setup-security").html()));
  }
});