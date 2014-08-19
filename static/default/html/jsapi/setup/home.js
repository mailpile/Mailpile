/* Setup - Home - Model */
var HomeModel = Backbone.Model.extend({
  validation: {}
});


/* Setup - Home - View */
var HomeView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  show: function() {
    this.$el.html(_.template($("#template-setup-home").html()));
  }
});