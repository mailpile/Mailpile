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
//    "keys"             : "keys",
//    "passphrase"       : "passphrase",
		"backups"          : "backups",
		"access"           : "access",
    "complete"         : "complete",
    "language"         : "language"
	},
	checkView: function(view) {
    var state = StateModel.checkState(view);
		if (view == state) {
      TooltipsView.showProgressCircles(view);
      return true;
		}
    else {
      TooltipsView.showProgressCircles(view);
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
  complete: function() {
    if (this.checkView('#complete')) {
      CompleteView.show();
    }
  },
  security: function() {
    SecurityView.show();
  },
/*
  keys: function() {
    KeysView.show();
  },
  passphrase: function() {
    PassphraseView.show();
  },
*/
  backups: function() {
    BackupsView.show();
  },
  access: function() {
    AccessView.show();
  },
  language: function() {
    LanguageView.show();
  }
});