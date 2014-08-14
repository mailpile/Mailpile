/* Setup - Importing - Model */
var ImportingModel = Backbone.Model.extend({
  validation: {}
});


/* Setup - Advanced - View */
var ImportingView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  show: function() {
    this.$el.html(_.template($('#template-setup-sources-importing').html(), {}));
  }
});