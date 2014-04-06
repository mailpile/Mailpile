var SetupRouter = Backbone.Router.extend(
{
	initialize: function(el) {

		this.el = el;

		// Generic Views
		this.indexView				= new ContentView('#index');
		this.logoutView				= new ContentView('#logout');
		this.notFoundView			= new ContentView('#not_found');

		// Record Views
		this.recordIndex			= new ContentView('#record');
		this.recordFeeling			= new RecordFeelingView({ el: $('#content') });

		// Settings Views
		this.settingsIndex			= new ContentView('#settings');
		this.settingsViews			= new SettingsView({ el: $('#content')});
	},
	routes: {
		"" 						: "index",
		"login" 				: "login",
		"signup"				: "signup",
		"forgot_password"		: "forgotPassword",
		"logout"				: "logout",
		"security"				: "securityViews",
		"security/:view"			: "recordViews"
	},
	currentView: null,
	switchView: function(view) {
		if (this.currentView) {
			this.currentView.remove();	// Detach the old view
		}

		this.el.html(view.el);			// Move the view element into the DOM (replacing the old content)
		view.render();					// Render view after it is in the DOM (styles are applied)
		this.currentView = view;
	},
	setActiveNav: function(url)	{	// For Main Nav Links and Shit
	    $.each(['record', 'visualize', 'settings'], function(key, value) {		
		    if (value == type) {
				$('#record_feeling_' + value).fadeIn();
			}
			else {
				$('#record_feeling_' + value).hide(); 
			}
	    });

	    // Do Control Buttons
	    $('div.left_control_links').removeClass('icon_small_text_on icon_small_emoticons_on icon_small_audio_on');
	    $('#log_feeling_use_' + type).addClass('icon_small_' +  type + '_on');
	},
	index: function() {
		if (UserData.get('logged') === 'yes') {
			Backbone.history.navigate('#record/feeling', true);	
		}
		else {
			this.switchView(this.indexView);
		}
	},
	recordViews: function(view) {
		if (UserData.get('logged') !== 'yes') {
			Backbone.history.navigate('#login', true);
		}
		else if (view === undefined) {
			this.switchView(this.recordIndex);
		}
		else if (view === 'feeling') {
			this.recordFeeling.viewFeeling();
		}
		else {
			this.switchView(this.notFoundView);
		}
	}
});