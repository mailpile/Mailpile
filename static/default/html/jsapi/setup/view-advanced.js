// Advanced View
var AdvancedView = Backbone.View.extend(
{
    initialize: function() {
  		this.render();
    },
    render: function(){},
    events: {
      "click #btn-setup-welcome-begin": "showAccess",
    },
    showAccess: function() {
      this.$el.html(_.template($("#template-setup-access").html()));
    },
    showSecurity: function() {
      this.$el.html(_.template($("#template-setup-security").html()));
    }
});