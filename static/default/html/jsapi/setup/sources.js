/* Setup - Sources - Model */
var SourceModel = Backbone.Model.extend({
  defaults: {
    _section: '', 
    action: '{{_("Add")}}',
    name: '',
    username: '',
    password: '',
    host: '',
    port: 993,
    protocol: '',
    interval: 300,
    'discovery.paths': [],
    'discovery.policy': 'unknown',
    'discovery.local_copy': true,
    'discovery.process_new': true,
    'discovery.create_tag': false,
    'discovery.apply_tags': ['']
  },
  validation: {
    name: {
      minLength: 2,
      required: true,
      msg: "{{_('Source Name')}}"      
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
    protocol: {
      oneOf: ["mbox", "maildir", "macmaildir", "gmvault", "imap", "imap_ssl", "pop3"],
      required: true,
      msg: "{{_('Mailbox protocol or format')}}"
    }, 
    interval: {
      required: false,
      msg: "{{_('How frequently to check for mail')}}"
    },
    'discovery.paths': {
      required: false,
      msg: "{{_('Paths to watch for new mailboxes')}}"
    },
    'discovery.policy': {
      oneOf: ['unknown', 'ignore', 'watch','read', 'move', 'sync'],
      required: false,
      msg: "{{_('Default mailbox policy')}}"
    },
    'discovery.local_copy': {
      required: false,
      msg: "{{_('Copy mail to a local mailbox?')}}"
    },
    'discovery.create_tag': {
      required: false,
      msg: "{{_('Create a tag for each mailbox?')}}"
    },
    'discovery.process_new': {
      required: false,
      msg: "{{_('Is a potential source of new mail')}}"
    },
    'discovery.apply_tags': {
      required: false,
      msg: "{{_('Tags applied to messages')}}"
    }
  }
});


var SourcesCollection = Backbone.Collection.extend({
  url: '/api/0/settings/as.json?var=sources',
  model: SourceModel
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
    "change #input-setup-source-type"  : "actionSelected",
    "change #input-setup-source_sync"  : "actionSyncSelected",
    "click #btn-setup-source-save"     : "processSource",
    "click #btn-setup-source-configure": "processConfigure",
    "click .setup-source-remove"       : "processRemove",
    "click #source-mailbox-read-all"   : "actionMailboxReadAll",
    "click .source-mailbox-policy"     : "actionMailboxToggle",
    "click #btn-setup-sources-next"    : "actionGoToImporting"
  },
  show: function() {

    this.$el.html(_.template($("#template-setup-sources").html()));

    // Load Data & Add to Collection
    Mailpile.API.settings_get({ var: 'sources' }, function(result) {

      // Redirect to Add
      if (_.isEmpty(result.result.sources)) {
        Backbone.history.navigate('#sources/add', true);
      }

      _.each(result.result.sources, function(val, key) {
        var source = new SourceModel(_.extend({id: key, action: '{{_("Edit")}}'}, val));
        SourcesCollection.add(source);
        $('#setup-sources-list-items').append(_.template($('#template-setup-sources-item').html(), source.attributes));
      });
    });

    return this;
  },
  showAdd: function() {
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    var source_id = Math.random().toString(36).substring(2);
    var NewSource = new SourceModel();
    NewSource.set({ _section: source_id, id: source_id, });
    this.$el.html(_.template($('#template-setup-sources-settings').html(), NewSource.attributes));
  },
  showEdit: function(id) {
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');

    Mailpile.API.settings_get({ var: 'sources.'+id }, function(result) {

      var source = result.result['sources.'+id];
      source = _.extend(source, {id: id, action: '{{_("Edit")}}'});
      $('#setup').html(_.template($('#template-setup-sources-settings').html(), source));
    });
  },
  showConfigure: function(id) {
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    Mailpile.API.settings_get({ var: 'sources.'+id }, function(result) {

      var source = result.result['sources.'+id];
      var mailbox_count = 0;
      var checked_count = 0;

      _.each(source.mailbox, function(mailbox, key) {
        mailbox_count ++;
        if (mailbox.policy == 'read' || mailbox.policy == 'unknown') {
          checked_count++;
        }
      });

      Mailpile.API.tags_get({}, function(result) {

        var special_tags = {};
        _.each(result.result.tags, function(tag, key) {
          if (_.indexOf(['inbox', 'drafts', 'sent', 'spam', 'trash'], tag.type) > -1) {
            special_tags[tag.type] = tag.tid;
          }
        });

        // Render HTML
        var configure = _.extend(source, { id: id, tags: result.result.tags, special_tags: special_tags });
        $('#setup').html(_.template($('#template-setup-sources-configure').html(), configure));

        // Select All (if all)
        if (mailbox_count === checked_count) {
          $('#source-mailbox-read-all').attr({'value': 'read', 'checked': true});
        }

        // Show Tooltips
        TooltipsView.showSourceConfigure();
      });
    });
  },
  showEvent: function(event) {

    // Default Message
    var message = event.message;

    // Connection / Behavior (message)
    if (event.data.connection.live && !event.data.connection.error[0]) {

      // Various Found or Is downloading
      if (event.data.copying && event.data.copying.running && event.data.copying.total) {
        message = '{{_("Downloading")}} ' + event.data.copying.copied_messages + ' {{_("of")}} ' + event.data.copying.total + ' {{_("messages")}}';
      } else if (event.data.copying && event.data.copying.running) {
        message = '{{_("Found some messages to download")}}';
      } else if (event.data.rescan) {
        message = '{{_("Rescanning mailboxes")}}';
      }
    }
    else if (!event.data.connection.live && !event.data.connection.error[0]) {
      message = '{{_("Not connected to server")}}';
    }
    else if (!event.data.connection.live && event.data.connection.error[0] == 'auth') {
      message =  '{{_("Can not connect to mailserver")}}';
      $('#setup-source-notice-' + event.data.id)
        .html('{{_("The username & password are incorrect")}} <a href="/setup/#sources/' + event.data.id + '">{{_("edit them now")}}</a>')
        .fadeIn();
    }
    else if (!event.data.connection.live && event.data.connection.error[0]) {
      message = event.data.connection.error[1];
    }


    // Has Unconfigured Mailboxes (action)
    if (event.data.have_unknown) {

      $('#setup-source-notice-' + event.data.id)
        .html('{{_("You have unconfigured mailboxes")}} <a href="/setup/#sources/configure/' + event.data.id + '">{{_("configure them now")}}</a>')
        .fadeIn();

      $('#btn-setup-sources-next').attr('disabled', true);
    } else {
      $('#btn-setup-sources-next').attr('disabled', false);
    }

    // UI Message
    $('#setup-source-message-' + event.data.id).html('<em>' + message + '</em>');

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
  actionMailboxReadAll: function(e) {
    if ($(e.target).is(':checked')) {
      _.each($('input.source-mailbox-policy'), function(val, key) {      
        $(val).attr('value', 'read').prop('checked', true);
      });
    } else {
      _.each($('input.source-mailbox-policy'), function(val, key) {      
        $(val).attr('value', 'ignore').prop('checked', false);
      });
    }
  },
  actionMailboxToggle: function(e) {
    if ($(e.target).is(':checked')) {
      $(e.target).attr('value', 'read').prop('checked', true);
    } else {
      $(e.target).attr('value', 'ignore').prop('checked', false);
    }
  },
  actionGoToImporting: function(e) {
    e.preventDefault();
    Backbone.history.navigate('#importing', true);
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
          SourcesView.model.set({name: '', username: '', password: '', port: ''});
          Backbone.history.navigate('#sources', true);
        } else {
          alert('Error saving Sources');
        }
      });
    }
  },
  processConfigure: function(e) {
    e.preventDefault();

    var mailbox_data = $('#form-setup-source-configure').serializeObject();

    // Set Unchecked Checkboxes
    _.each($('input.source-mailbox-policy:checkbox:not(:checked)'), function(val, key) {
      var name = $(val).attr('name');
      mailbox_data[name] = 'ignore';
    });

    // Validate & Process
    Mailpile.API.settings_set_post(mailbox_data, function(result) {
      if (result.status == 'success') {
        Backbone.history.navigate('#sources', true);
      } else {
        
      }
    });
  },
  processRemove: function(e) {
    e.preventDefault();
    var source_id = $(e.target).data('id');
    Mailpile.API.settings_unset_post({ rid: source_id }, function(result) {
      $('#setup-source-' + source_id).fadeOut();
    });
  }
});