/* Setup - Routes - Model */
var SendingModel = Backbone.Model.extend({
  url: '/api/0/settings/as.json?var=routes',
  defaults: {
    _section: '',
    command: '',
    name: '',
    login: '',
    password: '',
    host: '',
    port: 587,
    protocol: 'smtp'
  },
  validation: {
    name: {
      minLength: 2,
      required: true,
      msg: "{{_('Source Name')}}"      
    },
    login: {
      msg: "{{_('Login')}}"
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
  url: '/api/0/settings/as.json?var=routes',
  model: SendingModel
});


/* Setup - Routes - View */
var SendingView = Backbone.View.extend({
  initialize: function() {
    Backbone.Validation.bind(this);
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
        console.log(val);
        var sending = new SendingModel(_.extend({id: key, action: 'Edit'}, val));
        SourcesCollection.add(sending);
        $('#setup-sending-list-items').append(_.template($('#template-setup-sending-item').html(), sending.attributes));
      });
    });
  },
  showAdd: function() {
    $('#setup-sending-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    this.model.set({_section: 'routes.' + Math.random().toString(36).substring(2) })
    this.$el.html(_.template($("#template-setup-sending-settings").html(), this.model.attributes));
  },
  showEdit: function(id) {
    var sending = SendingCollection.get(id);
    if (sending !== undefined) {
      this.$el.html(_.template($("#template-setup-sending-settings").html(), sending.attributes));
    } else {
      Backbone.history.navigate('#sending', true);
    }
  },
  processSendingTest: function(e) {
    e.preventDefault();
    alert('This will at some point test a route');
    
  },
  processSending: function(e) {

    e.preventDefault();

    var sending_data = $('#form-setup-sending-settings').serializeObject();
    this.model.set(sending_data);

    // Validate & Process
    if (!this.model.validate()) {
      Mailpile.API.settings_set_post(sending_data, function(result) {
        Backbone.history.navigate('#sending', true);
      });
    }

  }
});