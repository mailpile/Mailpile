/* Setup - Routes - Model */
var SendingModel = Backbone.Model.extend({
  url: '/',
  validation: {
    name: {
      minLength: 2,
      required: true,
      msg: "{{_('Source Name')}}"      
    },
    protocol: {
      oneOf: ["smtp", "smtptls", "smtpssl", "local"],
      msg: "{{_('Specify a messaging protocol')}}"
    },
    username: {
      msg: "{{_('User name')}}"
    },
    password: {
      msg: "{{_('Password')}}",
    },
    command: {
      msg: "{{_('Shell command')}}"
    },
    host: {
      msg: "{{_('Specify a server')}}"
    },
    port: {
      required: true,
      msg: "{{_('Specify port')}}"
    }
  }
});


var SendingCollection = Backbone.Collection.extend({
  url: '/settings/as.json?var=routes',
  model: SendingModel
});


/* Setup - Routes - View */
var SendingView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  events: {
    "click #btn-setup-advanced-access" : "showRouteSettings",
    "click #btn-setup-sending-test"    : "processSendingTest",
    "click #btn-setup-sending-save"    : "processSending"
  },
  show: function() {

    this.$el.html(_.template($("#template-setup-sending").html()));

    // Load Data & Add to Collection
    Mailpile.API.settings_get({ var: 'routes' }, function(result) {

      if (_.isEmpty(result.result.routes)) {
        Backbone.history.navigate('#sending/add', true);
      }

      _.each(result.result.routes, function(val, key) {
        console.log(key);
        console.log(val);
//      var source = new SourceModel(_.extend({id: key, action: 'Edit'}, val));
//      SourcesCollection.add(source);
//      $('#setup-sources-list-items').append(_.template($('#template-setup-profiles-item').html(), source.attributes));
      });

    });

  },
  showAdd: function() {
    this.$el.html(_.template($("#template-setup-sending-settings").html(), { action: 'Add' }));
  },
  showEdit: function(id) {

    this.$el.html(_.template($("#template-setup-sending-settings").html(), { action: 'Edit' }));

  },
  processSendingTest: function(e) {
    e.preventDefault();
    alert('This will at some point test a route');
    
  },
  processSending: function(e) {

    e.preventDefault();

    var sending_data = $('#form-setup-sending-settings').serializeObject();
    //source_data = _.omit(source_data, 'source_type');
    var sending_id = Math.random().toString(36).substring(2);

    this.model.set(sending_data);

    // Validate & Process
    if (!this.model.validate()) {
/*
      Mailpile.API.setup_profiles_post(profile_data, function(result) {
        Backbone.history.navigate('#profiles', true);
      });
*/
    }

  }
});