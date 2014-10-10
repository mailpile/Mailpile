/* Setup - Language - View */
var LanguageView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  events: {
    "click #btn-setup-language-settings": "processLanguage",
  },
  show: function() {
    $('#setup').html($('#template-setup-language').html());
  },
  processLanguage: function(e) {
    e.preventDefault();
    var language_data = $('#form-setup-language').serializeObject();
    Mailpile.API.setup_welcome_post(language_data, function(result) {
      if (result.status == 'success') {
        window.location.replace('/setup/#');
      }
    });
  }
});