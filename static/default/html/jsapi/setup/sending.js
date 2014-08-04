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
  showAdd: function() {
    this.$el.html(_.template($("#template-setup-sending-settings").html(), { action: 'Add' }));
  },
  showEdit: function(id) {

    alert('ohai sending route settings');
    this.$el.html(_.template($("#template-setup-sending-settings").html(), { action: 'Edit' }));

  }
});