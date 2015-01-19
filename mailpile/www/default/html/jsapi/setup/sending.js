/* Setup - Routes - Model */
var SendingModel = Backbone.Model.extend({
  defaults: {
    _section: '',
    action: 'Add',
    complete: 'sending',
    command: '',
    name: '',
    username: '',
    password: '',
    host: '',
    port: 587,
    protocol: 'smtp'
  },
  validation: {
    name: {
      minLength: 2,
      required: true,
      msg: "{{_('You must name this route')}}"
    },
    username: {
      msg: "{{_('Username')}}"
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
      msg: "{{_('You must specify a port')}}"
    }
  }
});


var SendingCollection = Backbone.Collection.extend({
  url: '/api/0/settings/?var=routes&secrets=true',
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
    "click #btn-setup-advanced-access"   : "showRouteSettings",
    "change #route-add-port"             : "actionChangePort",
    "click #btn-setup-sending-check"     : "actionCheckAuth",
    "click #btn-setup-sending-back"      : "actionBack",
    "click #btn-setup-sending-save"      : "processSending",
    "click .setup-sending-remove"        : "processRemove"
  },
  show: function() {

    var sending_template = _.template($("#template-setup-sending").html());
    this.$el.html(sending_template());

    // Load Data & Add to Collection
    Mailpile.API.setup_profiles_get({}, function(result) {

      if (_.isEmpty(result.result.routes)) {
        Backbone.history.navigate('#sending/add', true);
      }

      var profile_routes = {};
      _.each(result.result.profiles, function(profile, profile_id) {
        if (_.has(profile_routes, profile.route_id)) {
          profile_routes[profile.route_id]++;
        } else {
          profile_routes[profile.route_id] = 1;
        }
      });

      _.each(result.result.routes, function(route, route_id) {
        if (route.name && route.host) {
          var sending = new SendingModel(_.extend({id: route_id, action: 'Edit', used_by: profile_routes[route_id] }, route));
          SourcesCollection.add(sending);
          var sending_item_template = _.template($('#template-setup-sending-item').html());
          $('#setup-sending-list-items').append(sending_item_template(sending.attributes));
        }
      });
    });
  },
  showAdd: function() {
    $('#setup-sending-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    this.model.set({id: Math.random().toString(36).substring(2) })
    var sending_settings_template = _.template($("#template-setup-sending-settings").html());
    this.$el.html(sending_settings_template(this.model.attributes));
  },
  showEdit: function(id) {
    $('#setup-box-source-list').removeClass('bounceInUp').addClass('bounceOutLeft');
    Mailpile.API.settings_get({ var: 'routes.'+id, secrets: true }, function(result) {
      var sending = result.result['routes.'+id];
      sending_data = _.extend(sending, { id: id, action: 'Edit', complete: 'sending' });
      var sending_template = _.template($('#template-setup-sending-settings').html());
      $('#setup').html(sending_template(sending_data));
    });
  },
  actionChangePort: function(e) {
    var port = $(e.target).val();
    if (port === 'other') {
      $(e.target).hide();
      $('#input-setup-sending-port').parent('span').fadeIn();
      $('#input-setup-sending-protocol').val('smtp');
    } else if (port == 465) {
      $('#input-setup-sending-port').val(port);
      $('#input-setup-sending-protocol').val('smtpssl');
    } else {
      $('#input-setup-sending-protocol').val('smtp');
      $('#input-setup-sending-port').val(port);
    }
  },
  actionCheckAuth: function(e) {
    e.preventDefault();

    // Status UI Message
    $('#setup-sending-check-auth')
      .removeClass('color-12-red color-08-green')
      .html('<em>{{_("Testing Credentials")}}</em> <img src="/static/css/select2-spinner.gif">');

    var sending_data = $('#form-setup-sending-settings').serializeObject();
    sending_data = _.omit(sending_data, '_section');

    Mailpile.API.setup_test_route_post(sending_data, function(result) {
       if (result.status ==  'success') {
          $('#setup-sending-check-auth')
            .removeClass('color-12-red')
            .addClass('color-08-green')
            .html('<span class="icon-checkmark"></span> {{_("Successfully Connected")}}');
        }
        else if (result.status == 'error') {
          $('#setup-sending-check-auth')
            .removeClass('color-08-green')
            .addClass('color-12-red')
            .html('<span class="icon-x"></span> {{_("Error Connecting")}}: '
                  + result.error.error);
        }
        setTimeout(function() {
          $('#setup-sending-check-auth')
            .removeClass('color-08-green color-12-red')
            .html('<a href="#" id="btn-setup-sending-check" class="setup-check-connection"><span class="icon-help"></span> {{_("Test Route")}}</a>');
        }, 5000);
    });
  },
  actionBack: function(e) {
    e.preventDefault();
    window.history.go(-1);
  },
  processSending: function(e) {

    e.preventDefault();

    var complete = $('#input-sending-complete').val();
    var sending_data = $('#form-setup-sending-settings').serializeObject();
    this.model.set(sending_data);

    // Validate & Process
    if (!this.model.validate()) {
      Mailpile.API.settings_set_post(sending_data, function(result) {
        if (complete === 'sending') {
          Backbone.history.navigate('#sending', true);        
        } else if (complete === 'profiles') { 
          ProfilesSettingsView.actionRouteAdded(sending_data._section.replace('routes.', ''), sending_data.name);
        }
      });
    }
  },
  processRemove: function(e) {
    e.preventDefault();
    var route_id = $(e.target).attr('href');
    Mailpile.API.settings_unset_post({var: 'routes.' + route_id }, function(result) {
      $('#setup-sending-' + route_id).fadeOut();
    });
  }
});
