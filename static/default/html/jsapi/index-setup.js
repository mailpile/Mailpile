/* JS App Files */
{% include("jsapi/setup/passphrase.js") %}
{% include("jsapi/setup/profiles.js") %}
{% include("jsapi/setup/sources.js") %}
{% include("jsapi/setup/sending.js") %}
{% include("jsapi/setup/advanced.js") %}
{% include("jsapi/setup/security.js") %}
{% include("jsapi/setup/backups.js") %}
{% include("jsapi/setup/access.js") %}
{% include("jsapi/setup/router.js") %}

/* Validation UI Feedback */
_.extend(Backbone.Validation.callbacks, {
  valid: function(view, attr, selector) {
    // do something
  },
  invalid: function(view, attr, error, selector) {
    $('#error-setup-' + attr).html(error);
  }
});

/* Main Init Call */
var SetupApp = (function ($, Backbone, global) {

    var init = function() {

      // Views
      global.PassphraseView = new PassphraseView({ model: new PassphraseModel(), el: $('#setup') });
      global.ProfilesView   = new ProfilesView({ model: new ProfilesModel(), el: $('#setup') });
      global.SourcesView    = new SourcesView({ model: new SourceModel(), el: $('#setup') });
      global.SendingView    = new SendingView({ el: $('#setup') });
      global.AdvancedView   = new AdvancedView({ el: $('#setup') });
      global.SecurityView   = new SecurityView({ el: $('#setup') });
      global.BackupsView    = new BackupsView({ el: $('#setup') });
      global.AccessView     = new AccessView({ el: $('#setup') });

  		// Router
  		global.Router = new SetupRouter($('#setup'));

      // Start Backbone History
      Backbone.history.start();
    };

    return { init: init };

} (jQuery, Backbone, window));