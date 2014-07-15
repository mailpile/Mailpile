/* JS App Files */
{% include("jsapi/setup/wizards.js") %}
{% include("jsapi/setup/pages.js") %}
{% include("jsapi/setup/setup.js") %}

/*
var Setup = (function ($, Backbone, global) {

    var init = function() {

        // URL
        global.base_url = '';
        global.assets_url = '';

        // Model
        global.EmoomeSettings  = new EmoomeSettings();
        global.UserData        = new UserData();
        global.UIMessages      = new UIMessages();
        global.LogFeelingModel = new LogFeelingModel();

        // Views
        global.Lightbox = new LightboxView({ el: $('body') });
        global.Navigation = new NavigationView({ el: $('#navigation') });
        global.AuthView	= new AuthView({ el: $('#content') });

		// Create Router
		global.Router = new ApplicationRouter($('#content'));
    
        // Start Backbone History
        Backbone.history.start();
    };

    return { init: init };

} (jQuery, Backbone, window));
*/