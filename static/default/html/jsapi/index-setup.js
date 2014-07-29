/* JS App Files */
{% include("jsapi/setup/passphrase.js") %}
{% include("jsapi/setup/profiles.js") %}
{% include("jsapi/setup/sources.js") %}
{# include("jsapi/setup/view-identity.js") #}
{# include("jsapi/setup/view-organize.js") #}
{% include("jsapi/setup/security.js") %}
{% include("jsapi/setup/access.js") %}
{% include("jsapi/setup/router.js") %}

var SetupApp = (function ($, Backbone, global) {

    var init = function() {

      // Model
      global.SourceModel = new SourceModel();

      // Views
      global.PassphraseView = new PassphraseView({ model: new PassphraseModel(), el: $('#setup') });
      global.ProfilesView   = new ProfilesView({ model: new ProfileModel(), el: $('#setup') });
      global.SourcesView    = new SourcesView({ el: $('#setup') });
//      global.IdentityView   = new IdentityView({ el: $('#setup') });
//      global.OrganizeView   = new OrganizeView({ el: $('#setup') });
      global.SecurityView   = new SecurityView({ el: $('#setup') });
      global.AccessView     = new AccessView({ el: $('#setup') });

  		// Router
  		global.Router = new SetupRouter($('#setup'));

      // Start Backbone History
      Backbone.history.start();
    };

    return { init: init };

} (jQuery, Backbone, window));
