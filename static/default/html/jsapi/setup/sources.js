/* Setup - Sources - Model */
var SourceModel = Backbone.Model.extend({
  validation: {
    name: {
      msg: "{{_('Source name')}}",
    },
    protocol: {
      oneOf: ["mbox", "maildir", "macmaildir", "gmvault", "imap", "imap_ssl", "pop3"],
      msg: "{{_('Mailbox protocol or format')}}"
    }, 
    interval: {
      msg: "{{_('How frequently to check for mail')}}"
    },
    username: {
      msg: "{{_('User name')}}"
    },
    password: {
      msg: "{{_('Password')}}"
    }, 
    host: {
      msg: "{{_('Host')}}"
    },
    port: {
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
    "click #btn-setup-source-add-cancel"   : "cancelAddSource",
  	"click #btn-setup-source-settings"     : "showSourceSettings"
  },
  show: function() {
    this.$el.html(_.template($("#template-setup-sources").html()));
  },
  showAddSource: function() {
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    this.$el.html(_.template($('#template-setup-source-settings').html()));
  },
  cancelAddSource: function(e) {
    e.prevenDefault();
    $('#setup-box-source-settings').removeClass('bounceInLeft').addClass('bounceOutLeft');    
    //Backbone.history.navigate('#sources', true);
  },
  showSourceSettings: function() {
    this.$el.html(_.template($('#template-setup-source-local-settings').html(), SourceModel.attributes));
  }
});