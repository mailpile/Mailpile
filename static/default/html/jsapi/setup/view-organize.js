// Organize View
var OrganizeView = Backbone.View.extend(
{
    initialize: function() {
  		this.render();
    },
    render: function(){},
    events: {
      "click #btn-setup-organize-source-settings": "showSourceSettings",
    },
    showSourceSettings: function() {
      this.$el.html(_.template($("#template-setup-organize-source-settings").html()));
    },
    processSourceSettings: function(e) {

      e.preventDefault();
      Backbone.history.navigate('#source-local', true);     
    },
    processSourceImport: function(e) {

      e.preventDefault();
      Backbone.history.navigate('#source-choose', true);
    }
});