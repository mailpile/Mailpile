// Setup Router
var SetupRouter = Backbone.Router.extend({
	initialize: function(el) {
		this.el = el;
	},
	routes: {
		"" 						     : "index",
		"passphrase"       : "passphrase",
		"crypto-generated" : "cryptoGenerated",
		"profiles"         : "profiles",
		"discovery"        : "discovery",
		"source-settings"  : "sourceSettings",
		"source-local"     : "sourceLocal",
		"source-choose"    : "sourceRemoteChoose",
		"access"           : "access",
		"security"         : "security"
	},
	index: function() {
    Backbone.history.navigate('#passphrase', true); 
  },
	passphrase: function() {
		PassphraseView.showPassphrase();
	},
	cryptoGenerated: function() {
		IdentityView.showCryptoGenerated();
	},
	profiles: function() {
		ProfilesView.showProfiles();
	},
  discovery: function() {
		IdentityView.showDiscovery();
  },
	sourceSettings: function() {
		sourceView.showSourceSettings();
	},
	sourceLocal: function() {
		IdentityView.showSourceLocal();
	},
	sourceRemoteChoose: function() {
		IdentityView.showSourceRemoteChoose();
	},
  access: function() {
    console.log('inside of access ROUTE');
    AdvancedView.showAccess();
  },
  security: function() {
    AdvancedView.showSecurity();
  }
});