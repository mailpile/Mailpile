/* JS App Files */
{% include("jsapi/setup/magic.js") %}
{% include("jsapi/setup/passphrase.js") %}
{% include("jsapi/setup/state.js") %}
{% include("jsapi/setup/home.js") %}
{% include("jsapi/setup/profiles.js") %}
{% include("jsapi/setup/profiles_settings.js") %}
{% include("jsapi/setup/sources.js") %}
{% include("jsapi/setup/sources_settings.js") %}
{% include("jsapi/setup/sources_configure.js") %}
{% include("jsapi/setup/sending.js") %}
{% include("jsapi/setup/security.js") %}
{% include("jsapi/setup/backups.js") %}
{% include("jsapi/setup/access.js") %}
{% include("jsapi/setup/importing.js") %}
{% include("jsapi/setup/tooltips.js") %}
{% include("jsapi/setup/router.js") %}

/* Validation UI Feedback */
_.extend(Backbone.Validation.callbacks, {
  valid: function(view, attr, selector) {
    var msg = $('#validation-' + attr).find('.validation-message').data('message');
    $('#validation-' + attr).find('.validation-message').html(msg).removeClass('validation-error');
    $('#validation-' + attr).find('[' + selector + '=' + attr +']').removeClass('validation-error');
  },
  invalid: function(view, attr, error, selector) {
    var message = $('#validation-' + attr).find('.validation-message').html();
    $('#validation-' + attr).find('.validation-message').data('message', message)
    $('#validation-' + attr).find('.validation-message').html(error).addClass('validation-error');
    $('#validation-' + attr).find('[' + selector + '=' + attr +']').addClass('validation-error');
  }
});

/* Main Init Call */
var SetupApp = (function ($, Backbone, global) {

    var init = function() {

      global.StateModel     = new StateModel();
      global.SecurityModel = new SecurityModel();

      global.ProfilesCollection = new ProfilesCollection();
      global.SourcesCollection  = new SourcesCollection();
      global.SendingCollection  = new SendingCollection();

      // Views
      global.HomeView       = new HomeView({ el: $('#setup') });
      global.ProfilesView   = new ProfilesView({ model: new ProfileModel(), el: $('#setup') });
      global.ProfilesSettingsView = new ProfilesSettingsView({ model: new ProfileModel(), el: $('#setup') });
      global.SourcesView          = new SourcesView({ el: $('#setup') });
      global.SourcesSettingsView  = new SourcesSettingsView({ model: new SourceModel(), el: $('#setup') });
      global.SourcesConfigureView = new SourcesConfigureView({ el: $('#setup') });
      global.SendingView    = new SendingView({ model: new SendingModel(), el: $('#setup') });
      global.SecurityView   = new SecurityView({ el: $('#setup') });
      global.BackupsView    = new BackupsView({ el: $('#setup') });
      global.AccessView     = new AccessView({ el: $('#setup') });
      global.ImportingView  = new ImportingView({ el: $('#setup') });
      global.TooltipsView   = new TooltipsView({ el: $('#setup') });

  		// Fetch State, Start Router
      StateModel.fetch({
        success: function(model) {
          global.Router = new SetupRouter({ state: model.attributes.result, el: $('#setup') });
          Backbone.history.start();
        }
      });

      // Global Tooltips
      TooltipsView.showProgress();

      // Eventlog Polling
      var Events = {};
      Events = $.timer(function() {

        // Get Events
        Mailpile.API.eventlog_get({incomplete: 1}, function(result) {
          if (result.status == 'success') {
            _.each(result.result.events, function(event, key) {

              // Mailsource & Sources Page
              if (Backbone.history.fragment === 'sources') {
                if (_.indexOf(['.mail_source.imap.ImapMailSource'], event.source) > -1) {
                  SourcesView.eventUnconfigured(event);
                  SourcesView.eventRemote(event);
                }
                else if (_.indexOf(['.mail_source.maildir.MaildirMailSource', '.mail_source.mbox.MboxMailSource'], event.source) > -1) {
                  SourcesView.eventUnconfigured(event);
                  SourcesView.eventLocal(event);
                }
              }

              // Mailsource & Importing Page
              if (event.source.indexOf(".mail_source.") > -1 && Backbone.history.fragment === 'importing') {
                //ImportingView.showEvent(event);
              }
            });
          }
        });  
      });
  
      Events.set({ time : 7500, autostart : true });
      Events.play();
    };

    return { init: init };

} (jQuery, Backbone, window));
