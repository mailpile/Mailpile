// Setup Router
var SetupRouter = Backbone.Router.extend({
	initialize: function(el) {
		this.el = el;
	},
	routes: {
		"" 						     : "index",
		"profiles"         : "profiles",
		"profiles/add"     : "profilesAdd",
		"profiles/:id"     : "profilesEdit",
		"crypto-generated" : "cryptoGenerated",
		"discovery"        : "discovery",
    "sources"          : "sources",
    "sources/add"      : "sourcesAdd",
    "sources/:id"      : "sourcesEdit",
    "sources/configure/:id" : "sourcesConfigure",
		"sending"          : "sending",
		"sending/add"      : "sendingAdd",
    "sending/:id"      : "sendingEdit",
		"advanced"         : "advanced",
		"security"         : "security",
		"backups"          : "backups",
		"access"           : "access",
    "importing"        : "importing"
	},
	index: function() {
    if ($('#setup-profiles-count').val() > 0) {
      Backbone.history.navigate('#profiles', true);
    } else {
      Backbone.history.navigate('#profiles/add', true);
    }
  },
	profiles: function() {
		ProfilesView.show();
	},
	profilesAdd: function() {
		ProfilesView.showAdd();
	},
  profilesEdit: function(id) {
    ProfilesView.showEdit(id);
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
    SourcesView.showAdd();
  },
  sourcesEdit: function(id) {
    SourcesView.showEdit(id);
  },
  sourcesConfigure: function(id) {
    SourcesView.showConfigure(id);
  },
	sending: function() {
		SendingView.show();
	},
  sendingAdd: function() {
    SendingView.showAdd();
  },
  sendingEdit: function(id) {
    SendingView.showEdit(id);
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
  },
  importing: function() {
    ImportingView.show();
  }
});