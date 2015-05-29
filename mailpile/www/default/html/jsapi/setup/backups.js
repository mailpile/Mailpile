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
  events: {},
  show: function() {
    var backups_template = _.template($("#template-setup-backups").html());
    this.$el.html(backups_template);
  }
});