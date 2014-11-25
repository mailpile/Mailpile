/* Setup - Profiles - Model */
var ProfileModel = Backbone.Model.extend({
  defaults: {
    id: 'new',
    action_i18n: '{{_("Add")}}',
    action: 'Add',
    warning: 'none',
    name: '',
    email: '',
    pass: '',
    note: '',
    route_id: ''
  },
  validation: {
    name: {
      minLength: 1,
      maxLength: 48,
      required: true,
      msg: '{{_("Enter a name for your profile")}}'
    },
    email: {
      maxLength: 128,
      pattern: 'email',
      required: true,
      msg: '{{_("Enter a valid email address")}}'
    },
    pass: {
      required: false
    },
    route_id: {
      minLength: 1,
      required: true,
      msg: '{{_("Create or select a sending route")}}'
    },
    note: {
      maxLength: 48,
      required: false
    },
    auto_configurable: false,
    pgp_keys: []
  }
});


var ProfilesCollection = Backbone.Collection.extend({
  url: '/api/0/setup/profiles/',
  model: ProfileModel
});


/* Setup - Profiles - View */
var ProfilesView = Backbone.View.extend({
  initialize: function() {
    Backbone.Validation.bind(this);
    this.render();
  },
  render: function() {
    return this;
  },
  events: {
    "click #btn-setup-show-add-profile"   : "showAdd",
    "click .setup-profile-remove"         : "processRemove"
  },
  show: function() {

    this.$el.html($('#template-setup-profiles').html());

    // Load Data & Add to Collection
    Mailpile.API.setup_profiles_get({}, function(result) {

      if (!_.isEmpty(result.result.profiles)) {

        $('#setup-profiles-list-description').hide();

        // Can Go Next
        var can_next = [];
        _.each(result.result.profiles, function(val, key) {
          if (val.route_id) {
            can_next.push(true); 
          } else {
            can_next.push(false);
          }
  
          var profile = new ProfileModel(_.extend({id: key, action: 'Edit', action_i18n: '{{_("Edit")}}'}, val));
          ProfilesCollection.add(profile);
          var profile_template = _.template($('#template-setup-profiles-item').html());
          $('#setup-profiles-list-items').append(profile_template(profile.attributes));
        });
  
        // Hide Delete (if only 1 profile)
        if (ProfilesCollection.length === 1) {
          $('.setup-profile-remove').parent().hide();
        }
  
        // Display (or not) Button
        if (StateModel.attributes.result.complete) {
          $('#setup-profiles-list-buttons').hide();
        }
        else if (_.indexOf(can_next, true) > -1) {
          $('#btn-setup-profiles-next').show();
        } else {
          $('#setup-profiles-no-next').show();
        }

      } else {
        $('#setup-profiles-list-buttons').hide();
        $('#setup-profiles-list-items').hide();
      }
    });

    return this;
  },
  processRemove: function(e) {
    e.preventDefault();
    var profile_id = $(e.target).data('id');
    Mailpile.API.profiles_remove_post({ rid: profile_id }, function(result) {
      $('#setup-profile-' + profile_id).fadeOut(function() {
        $(this).remove();
      });
      if ($('#setup-profiles-list-items li.setup-item').length === 1) {
        $('.setup-profile-remove').parent().hide();
      }
    });
  }
});
