/* Setup - Sources - Model */
var SourceModel = Backbone.Model.extend({
  validation: {
    name: {
      minLength: 2,
      required: true,
      msg: "{{_('Source Name')}}"      
    },
    protocol: {
      oneOf: ["mbox", "maildir", "macmaildir", "gmvault", "imap", "imap_ssl", "pop3"],
      required: true,
      msg: "{{_('Mailbox protocol or format')}}"
    }, 
    interval: {
      msg: "{{_('How frequently to check for mail')}}"
    },
    username: {
      required: false,
      msg: "{{_('User name')}}"
    },
    password: {
      required: false,
      msg: "{{_('Password')}}"
    }, 
    host: {
      required: false,
      msg: "{{_('Host')}}"
    },
    port: {
      required: false,
      msg: "{{_('Port')}}"
    },
    'discovery.paths': {
      msg: "{{_('Paths to watch for new mailboxes')}}"
    },
    'discovery.policy': {
      oneOf: ['unknown', 'ignore', 'watch','read', 'move', 'sync'],
      msg: "{{_('Default mailbox policy')}}"
    },
    'discovery.local_copy': {
      msg: "{{_('Copy mail to a local mailbox?')}}"
    },
    'discovery.create_tag': {
      msg: "{{_('Create a tag for each mailbox?')}}"
    },
    'discovery.process_new': {
      msg: "{{_('Is a potential source of new mail')}}"
    },
    'discovery.apply_tags': {
      msg: "{{_('Tags applied to messages')}}"
    }
  }
});


/* Setup - Sources - View */
var SourcesView = Backbone.View.extend({
  initialize: function() {
    Backbone.Validation.bind(this);
		this.render();
  },
  render: function() {
    return this;
  },
  events: {
  	"click #btn-setup-source-settings"  : "showSourceSettings",
    "change #input-setup-source-type"   : "actionSourceSelected",
    "change #input-setup-source_sync"   : "actionSyncSelected",
    "click #btn-setup-source-save"      : "processSource"
  },
  show: function() {

    this.$el.html(_.template($("#template-setup-sources").html()));

    // Load Data & Add to Collection
    Mailpile.API.settings_get({ var: 'sources' }, function(result) {

      if (_.isEmpty(result.result.sources)) {
        Backbone.history.navigate('#sources/add', true);
      }

      _.each(result.result.sources, function(val, key) {
//        var source = new SourceModel(_.extend({id: key, action: 'Edit'}, val));
//        SourcesCollection.add(source);
//        $('#setup-sources-list-items').append(_.template($('#template-setup-profiles-item').html(), source.attributes));
      });
    });

  },
  showAddSource: function() {
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    this.$el.html(_.template($('#template-setup-source-settings').html()));
  },
  showEditSource: function(id) {

  },
  showSourceSettings: function() {
    this.$el.html(_.template($('#template-setup-source-local-settings').html(), SourceModel.attributes));
  },
  actionSourceSelected: function(e) {

    if ($(e.target).val() == 'local') {
      $('#setup-source-settings-server').hide();
      $('#setup-source-settings-local').fadeIn().removeClass('hide');
      $('#setup-source-settings-details').fadeIn().removeClass('hide');
    }
    else if ($(e.target).val() == 'remote') {
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
  processSource: function(e) {

    e.preventDefault();

    if ($(e.target).data('id') == 'new') {

      // Update Model
      var source_data = $('#form-setup-source-settings').serializeObject();
      this.model.set(source_data);

      console.log(source_data);
  
      // Validate & Process
      if (!this.model.validate()) {
/*
        Mailpile.API.setup_profiles_post(profile_data, function(result) {
          Backbone.history.navigate('#profiles', true);
        });
*/
      }
    }
    
  }
});