/* Setup - Home - View */
var HomeView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  show: function() {
    var home_template = _.template($("#template-setup-home").html());
    this.$el.html(home_template);
  }
});