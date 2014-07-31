// Setup Router
var SetupRouter = Backbone.Router.extend({
	initialize: function(el) {
		this.el = el;
	},
	routes: {
		"" 						     : "index",
		"passphrase"       : "passphrase",
		"profiles"         : "profiles",
		"crypto-generated" : "cryptoGenerated",
		"discovery"        : "discovery",
    "sources"          : "sources",
		"sending"          : "sending",
		"advanced"         : "advanced",
		"security"         : "security",
		"backups"          : "backups",
		"access"           : "access"
	},
	index: function() {
    Backbone.history.navigate('#passphrase', true); 
  },
	passphrase: function() {
		PassphraseView.show();
	},
	profiles: function() {
		ProfilesView.show();
	},
  discovery: function() {
		IdentityView.showDiscovery();
  },
	cryptoGenerated: function() {
		IdentityView.showCryptoGenerated();
	},
  sources: function() {
    SourcesView.show();
  },
	sending: function() {
		SendingView.show();
	},
  advanced: function() {
    AdvancedView.show();
  },
  security: function() {
    SecurityView.show();
  },
  backups: function() {
    BackupsView.show();
  },
  access: function() {
    AccessView.show();
  }
});