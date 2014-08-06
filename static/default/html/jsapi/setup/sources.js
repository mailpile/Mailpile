/* Setup - Sources - Model */
var SourceModel = Backbone.Model.extend({
  url: '/settings/',
  defaults: {
    _section: '', 
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
  url: '/settings/as.json?var=sources',
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
    "click #source-mailbox-read-all"   : "actionMailboxReadAll"
  },
  show: function() {

    this.$el.html(_.template($("#template-setup-sources").html()));

    // Load Data & Add to Collection
    Mailpile.API.settings_get({ var: 'sources' }, function(result) {

      if (_.isEmpty(result.result.sources)) {
        Backbone.history.navigate('#sources/add', true);
      }

      _.each(result.result.sources, function(val, key) {
        var source = new SourceModel(_.extend({id: key, action: 'Edit'}, val));
        SourcesCollection.add(source);
        $('#setup-sources-list-items').append(_.template($('#template-setup-sources-item').html(), source.attributes));
      });

    });

    return this;
  },
  showAdd: function() {
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    this.model.set({_section: 'sources.' + Math.random().toString(36).substring(2) })
    this.$el.html(_.template($('#template-setup-sources-settings').html(), this.model.attributes));
  },
  showEdit: function(id) {
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    var source = SourcesCollection.get(id);
    if (source !== undefined) {
      this.$el.html(_.template($('#template-setup-sources-settings').html(), source.attributes));
    } else {
      Backbone.history.navigate('#sources', true);
    }
  },
  showConfigure: function(id) {
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    var source = SourcesCollection.get(id);
    if (source !== undefined) {

      this.$el.html(_.template($('#template-setup-sources-configure').html(), source.attributes));
    } else {
      Backbone.history.navigate('#sources', true);
    }
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
        $(val).attr({'value': 'read', 'checked': true});
      });
    } else {
      _.each($('input.source-mailbox-policy'), function(val, key) {      
        $(val).attr({'value': 'ignore', 'checked': false});
      });
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

    // Update Model
    var source_data = $('#form-setup-source-settings').serializeObject();
    source_data = _.omit(source_data, 'source_type');
    console.log(source_data);

    this.model.set(source_data);

    // Validate & Process
    if (!this.model.validate()) {
      Mailpile.API.settings_set_post(source_data, function(result) {
        if (result.status == 'success') {
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
    console.log(mailbox_data);

    // Validate & Process
    Mailpile.API.settings_set_post(mailbox_data, function(result) {
      if (result.status == 'success') {

        //Backbone.history.navigate('#sources', true);
      } else {
        alert('Error saving Sources');          
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