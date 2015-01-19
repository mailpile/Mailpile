/* Setup - Sources Configure - View */
var SourcesConfigureView = Backbone.View.extend({
  initialize: function() {
//    Backbone.Validation.bind(this);
		this.render();
  },
  render: function() {
    return this;
  },
  events: {
    "click #source-mailbox-read-all"   : "actionMailboxReadAll",
    "click .source-mailbox-policy"     : "actionMailboxToggle",
    "click #btn-setup-source-configure": "processConfigure"
  },
  show: function(id) {
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
        var configure_template = _.template($('#template-setup-sources-configure').html());
        $('#setup').html(configure_template(configure));

        // Select All (if all)
        if (mailbox_count === checked_count) {
          $('#source-mailbox-read-all').attr({'value': 'read', 'checked': true});
        }

        // Show Tooltips
        TooltipsView.showSourceConfigure();
      });
    });
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
  }
});