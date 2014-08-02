// Setup Router
var SetupRouter = Backbone.Router.extend({
	initialize: function(el) {
		this.el = el;
	},
	routes: {
		"" 						     : "index",
		"profiles"         : "profiles",
		"profiles-add"     : "profilesAdd",
		"crypto-generated" : "cryptoGenerated",
		"discovery"        : "discovery",
    "sources"          : "sources",
    "sources-add"      : "sourcesAdd",
		"sending"          : "sending",
		"advanced"         : "advanced",
		"security"         : "security",
		"backups"          : "backups",
		"access"           : "access"
	},
	index: function() {
    Backbone.history.navigate('#profiles', true);
  },
	profiles: function() {
		ProfilesView.show();
	},
	profilesAdd: function() {
		ProfilesView.showAddProfile();
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
  sourcesAdd: function() {
    SourcesView.showAddSource();
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