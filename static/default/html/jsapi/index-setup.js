/* JS App Files */
{# include("jsapi/setup/wizards.js") #}
{# include("jsapi/setup/pages.js") #}
{# include("jsapi/setup/setup.js") #}

{% include("jsapi/setup/model.js") %}
{% include("jsapi/setup/view.js") %}
{% include("jsapi/setup/router.js") %}

var SetupApp = (function ($, Backbone, global) {

    var init = function() {

      // Model
      global.SetupModel = new SetupModel();
      global.CryptoModel = new CryptoModel();
      global.SourceModel = new SourceModel();

      // Views
      global.SetupView = new SetupView({ el: $('#setup') });
      global.SettingsView = new SettingsView({ el: $('#setup') });

  		// Router
  		global.Router = new SetupRouter($('#setup'));

      // Start Backbone History
      Backbone.history.start();
    };

    return { init: init };

} (jQuery, Backbone, window));
