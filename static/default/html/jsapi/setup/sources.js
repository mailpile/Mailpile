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
      msg: "{{_('You must pick a protocol or format')}}"
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
  model: SourceModel,
  can_next: false
});


/* Setup - Sources - View */
var SourcesView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function() {
    return this;
  },
  events: {
    "change #input-setup-source-type"  : "actionSelected",
    "change #input-setup-source_sync"  : "actionSyncSelected",
    "click .source-mailbox-policy"     : "actionMailboxToggle",
    "click #btn-setup-source-save"     : "processSource",
    "click .setup-source-disable"      : "processDisable"
  },
  show: function() {

    this.$el.html(_.template($("#template-setup-sources").html()));

    // Load Data & Add to Collection
    Mailpile.API.settings_get({ var: 'sources' }, function(result) {

      // Redirect to Add
      if (_.isEmpty(result.result.sources)) {
        Backbone.history.navigate('#sources/add', true);
      }

      // Loop Sources
      var can_next = [];
      _.each(result.result.sources, function(val, key) {

        // Tally CanNext
        if (!_.isEmpty(val.mailbox) && val.enabled) {
          can_next.push(true); 
        } else {
          can_next.push(false);
        }

        // Render HTML Items
        var source = new SourceModel(_.extend({id: key, action: '{{_("Edit")}}'}, val));
        SourcesCollection.add(source);
        $('#setup-sources-list-items').append(_.template($('#template-setup-sources-item').html(), source.attributes));
      });

      // Display (or not) Next Button
      if (StateModel.attributes.result.complete) {
        $('#setup-profiles-list-buttons').hide();
      }
      else if (StateModel.attributes.result.sources === true && _.indexOf(can_next, true) > -1) {
        SourcesCollection.can_next = true;
      } else {
        $('#setup-sources-not-configured').show();
      }
    });

    return this;
  },
  eventUnconfigured: function(event) {

    // Has Unconfigured Mailboxes (action)
    if (event.data.have_unknown) {
      $('#setup-item-notice-' + event.data.id)
        .html('{{_("Source has unconfigured mailboxes")}} <a href="/setup/#sources/configure/' + event.data.id + '" class="right"><span class="icon-signature-unknown"></span> {{_("Configure Now")}}</a>')
        .fadeIn();

      $('#setup-sources-analyzing').hide();
      $('#setup-sources-next-state').html('{{_("You need at least one mail source configured!")}}');
    }
    // Show Next
    else if (SourcesCollection.can_next && StateModel.attributes.result.sources) {
      $('#setup-sources-next-state').hide();
      $('#btn-setup-sources-next').show();
    }
  },
  eventProcessing: function(event) {

    var message = '{{_("No new messages")}}';

    // Is Copying
    if (event.data.copying) {
      if (event.data.copying && event.data.copying.total) {

        // Mailbox
        var name = '{{_("mailbox")}}';
        var source = SourcesCollection.get(event.data.id);
        if (source) {
          var name = source.attributes.mailbox[event.data.copying.mailbox_id].name;
        }

        message = '{{_("Downloaded")}} ' + event.data.copying.copied_messages + ' {{_("of")}} ' + event.data.copying.total + ' {{_("from")}} ' + name;
      } else if (event.data.copying && event.data.copying.running) {
        message = '{{_("Found messages to download")}}';
      } else if (event.data.copying && event.data.copying.complete) {
        message = '{{_("Mailbox up to date")}}';
      } else {
        message = '{{_("Copying new messages")}}';
      }
    }
    // Is Recanning
    else if (event.data.rescan) {
      if (event.data.rescan.running) {
        message = '{{_("Rescanning mailboxes")}}';
      }
      else if (event.data.rescan.added) {
        message = event.data.rescan.added + ' {{_("Messages imported")}}';
      } else if (event.data.rescan.total) {
        message = event.data.rescan.total + ' {{_("Messages")}}';
      } else {
        message = '{{_("Done scaning mailboxes")}}';
      }
    }

    return message;
  },
  eventRemote: function(event) {

    // Default Message
    var message = event.message;

    // Connection / Behavior (message)
    if (event.data.connection && event.data.connection.live && !event.data.connection.error[0]) {
      message = this.eventProcessing(event);
    }
    else if (event.data.connection.error[0] == 'auth') {
      message =  '{{_("Can not connect to server")}}';
      $('#setup-item-notice-' + event.data.id)
        .html(event.data.connection.error[1] + ' <a href="/setup/#sources/' + event.data.id + '" class="right"><span class="icon-signature-unknown"></span> {{_("Edit Now")}}</a>')
        .fadeIn();
    }
    else if (!event.data.connection.live && !event.data.connection.error[0]) {
      message = '{{_("Not connected to server")}}';
    }
    else if (!event.data.connection.live && event.data.connection.error[0]) {
      message = event.data.connection.error[1];
    }

    // UI Message
    $('#setup-source-message-' + event.data.id).html('<em>' + message + '</em>');
  },
  eventLocal: function(event) {

    var message = this.eventProcessing(event);

    // UI Message
    $('#setup-source-message-' + event.data.id).html('<em>' + message + '</em>');
  },
  processDisable: function(e) {
    e.preventDefault();
    var source_id   = $(e.target).data('id');
    var old_message = $(e.target).html();
    var new_message = $(e.target).data('message');

    if ($(e.target).data('state')) {
      var state = false;
    } else {
      var state = true;
    }

    var source_data = {};
    source_data['sources.' + source_id + '.enabled'] = state;
    Mailpile.API.settings_set_post(source_data, function(result) {
      if (result.status === 'success') {
        if (!state) {
          $('#setup-source-' + source_id).addClass('disabled');
        } else {
          $('#setup-source-' + source_id).removeClass('disabled');
        }
        $(e.target).html(new_message);
        $(e.target).data('state', state);
        $(e.target).data('message', old_message);
      }
    });
  }
});