// Setup Router
var SetupRouter = Backbone.Router.extend({
	initialize: function(options) {
    this.state = options.state;
    this.el = options.el;
    this.index();
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
	checkView: function(view) {
    var state = StateModel.checkState(view);
		if (view == state) {
      return true;
		}
    else {
      Backbone.history.navigate(state, true);
    }
	},
	index: function() {
    if (this.checkView('#')) {
      HomeView.show();
    }
  },
	profiles: function() {
    if (this.checkView('#profiles')) {
      ProfilesView.show();
    }
	},
	profilesAdd: function() {
		ProfilesSettingsView.show();
	},
  profilesEdit: function(id) {
    ProfilesSettingsView.showEdit(id);
  },
  sources: function() {
    if (this.checkView('#sources')) {
      SourcesView.show();
    }
  },
  sourcesAdd: function() {
    if (this.checkView('#sources/add')) {
      SourcesSettingsView.show();
    }
  },
  sourcesEdit: function(id) {
    SourcesSettingsView.showEdit(id);
  },
  sourcesConfigure: function(id) {
    SourcesConfigureView.show(id);
  },
	sending: function() {
    if (this.checkView('#sending')) {
      SendingView.show();
    }
	},
  sendingAdd: function() {
    SendingView.showAdd();
  },
  sendingEdit: function(id) {
    SendingView.showEdit(id);
  },
  importing: function() {
    console.log('here inside importing()');
    if (this.checkView('#importing')) {
      ImportingView.show();
    }
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
});