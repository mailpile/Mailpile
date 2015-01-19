/* Setup - Advanced - Model */
var AdvancedModel = Backbone.Model.extend({
  validation: {}
});


/* Setup - Advanced - View */
var AdvancedView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  show: function() {
    this.$el.html(_.template($("#template-setup-advanced").html()));
  }
});