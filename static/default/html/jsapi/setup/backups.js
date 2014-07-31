/* Setup - Backups - Model */
var BackupsModel = Backbone.Model.extend({
  validation: {}
});


/* Setup - Backups - View */
var BackupsView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  events: {
  },
  show: function() {
    this.$el.html(_.template($("#template-setup-backups").html()));
  }
});