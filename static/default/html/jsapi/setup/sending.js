/* Setup - Routes - Model */
var SendingModel = Backbone.Model.extend({
  validation: {
  }
});


/* Setup - Routes - View */
var SendingView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  events: {
    "click #btn-setup-advanced-access": "showRouteSettings",
  },
  show: function() {
    this.$el.html(_.template($("#template-setup-sending").html()));
  },
  showSendingSettings: function() {
    alert('ohai sending route settings');
  }
});