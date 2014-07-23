// Setup Router
var SetupRouter = Backbone.Router.extend(
{
	initialize: function(el) {
		this.el = el;
	},
	routes: {
		"" 						     : "index",
		"password"         : "password",
		"profiles"         : "profiles",
		"discovery"        : "discovery",
		"crypto-found"     : "cryptoFound",
		"crypto-generated" : "cryptoGenerated",
		"source-settings"  : "sourceSettings",
		"source-local"     : "sourceLocal",
		"source-choose"    : "sourceRemoteChoose",
		"access"           : "access",
		"security"         : "security"
	},
	index: function() {
		IdentityView.showIndex();
	},
	password: function() {
		IdentityView.showPassword();
	},
	profiles: function() {
		IdentityView.showProfiles();
	},
  discovery: function() {
		IdentityView.showDiscovery();
  },
	cryptoFound: function() {
		IdentityView.showCryptoFound();
	},
	cryptoGenerated: function() {
		IdentityView.showCryptoGenerated();
	},
	sourceSettings: function() {
		IdentityView.showSourceSettings();
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