/* Setup - Sources Settings - View */
var SourcesSettingsView = Backbone.View.extend({
  initialize: function() {
    Backbone.Validation.bind(this);
		this.render();
  },
  render: function() {
    return this;
  },
  events: {
    "change #input-setup-source-type"    : "actionSelected",
    "change #input-setup-source_sync"    : "actionSyncSelected",
    "click .source-mailbox-policy"       : "actionMailboxToggle",
    "keyup #input-setup-source-username" : "actionCheckEmailMagic",
    "click #btn-setup-source-save"       : "processSource"
  },
  show: function() {
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    var source_id = Math.random().toString(36).substring(2);
    var NewSource = new SourceModel();
    NewSource.set({ _section: source_id, id: source_id, });
    var source_template = _.template($('#template-setup-sources-settings').html());
    this.$el.html(source_template(NewSource.attributes));
  },
  showEdit: function(id) {
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');

    Mailpile.API.settings_get({ var: 'sources.'+id, secrets: true }, function(result) {

      var source = result.result['sources.'+id];
      source = _.extend(source, {id: id, action: '{{_("Edit")}}'});
      var source_template = _.template($('#template-setup-sources-settings').html());
      $('#setup').html(source_template(source));
    });
  },
  actionSelected: function(e) {
    if ($(e.target).val() == 'local') {
      $('#setup-source-settings-server').hide();
      $('#setup-source-settings-local').fadeIn().removeClass('hide');
      $('#setup-source-settings-details').fadeIn().removeClass('hide');
    }
    else if ($(e.target).val() == 'server') {
      $('#setup-source-settings-local').hide();
      $('#setup-source-settings-server').fadeIn().removeClass('hide');
      $('#setup-source-settings-details').fadeIn().removeClass('hide');
    }
    else {
      $('#setup-source-settings-local').hide();
      $('#setup-source-settings-server').hide();
      $('#setup-source-settings-details').hide();      
    }
  },
  actionSyncSelected:  function(e) {
    if ($(e.target).val() == 'once') {
      $('#setup-source-settings-sync-interval').hide();
    }
    else if ($(e.target).val() == 'sync'){
      $('#setup-source-settings-sync-interval').fadeIn().removeClass('hide');
    }
  },
  actionCheckEmailMagic: function(e) {
    var domain = $(e.target).val().replace(/.*@/, "");
    var provider = SetupMagic.providers[domain];

    if (provider) {
      var magic = SetupMagic.presets[provider];
      $('#form-setup-source-settings').find('input[name=host]').val(magic.source.host);
      $('#form-setup-source-settings').find('input[name=port]').val(magic.source.port);
      $('#input-setup-source-server-protocol').val(magic.source.protocol);

      // Show Gmail Warning
      if (provider === 'gmail') {
        ProfilesSettingsView.showGmailWarning('warning');
      }
    }
  },
  processSource: function(e) {
    e.preventDefault();

    if ($('#input-setup-source-type').val() == 'local') {
      $('#input-setup-source-server-protocol').remove();
      $('#input-setup-source-server-local_copy').remove();
    }
    else if ($('#input-setup-source-type').val() == 'server') {
      $('#input-setup-source-local-protocol').remove();
      $('#input-setup-source-local-local_copy').remove();
    }

    // Get, Prep, Update Model
    var source_data = $('#form-setup-source-settings').serializeObject();
    source_data = _.omit(source_data, 'source_type');
    this.model.set(source_data);

    // Validate & Process
    if (!this.model.validate()) {
      Mailpile.API.settings_set_post(source_data, function(result) {
        if (result.status == 'success') {

          // Reset Model
          StateModel.fetch({
            success: function(model) {
              SourcesSettingsView.model.set({name: '', username: '', password: '', port: ''});
              Backbone.history.navigate('#sources', true);
            }
          });
        } else {
          alert('Error saving Sources');
        }
      });
    }
  },
});