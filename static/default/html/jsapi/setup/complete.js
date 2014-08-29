/* Setup - Complete - Model */
var CompleteModel = Backbone.Model.extend({
  validation: {}
});


/* Setup - Complete - View */
var CompleteView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  show: function() {
    Mailpile.API.settings_set_post({ 'web.setup_complete': true }, function(result) {
      $('#setup').html(_.template($('#template-setup-sources-importing').html(), {}));
    });
  }
});