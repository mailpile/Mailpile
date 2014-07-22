// Setup Model
var SetupModel = Backbone.Model.extend({
    defaults: {
      install_type: '',
      name: '',
      password: ''
    },
    initialize: function() {}
});


var CryptoModel = Backbone.Model.extend({
    defaults: {
      public_key_count: 3000,
      private_key_count: 2,
      fingerprint: 'E412A4F7G2D4C1A9'
    },
    initialize: function() {}
});


var SourceModel = Backbone.Model.extend({
    defaults: {
      source_type: "Thunderbird",
      source_items: [{
          name: "Friends & Family",
          count: 3672,
          path: "/Users/brennannovak/Library/Mail/Folders/friends-family.mbox"
        },{
          name: "Work Stuff",
          count: 7271,
          path: "/Users/brennannovak/Library/Mail/Folders/work-stuff.mbox"
        },{
          name: "Conferences",
          count: 392,
          path: "/Users/brennannovak/Library/Mail/Folders/conferences.mbox"
        },{
          name: "Important Stuff",
          count: 1739,
          path: "/Users/brennannovak/Library/Mail/Folders/important-stuff.mbox"
        },{
          name: "Really Important Stuff",
          count: 445,
          path: "/Users/brennannovak/Library/Mail/Folders/really-important-stuff.mbox"
        },{
          name: "Old Archive",
          count: 128342,
          path: "/Users/brennannovak/Library/Mail/Folders/old-archive.mbox"
        }
      ]
    },
    initialize: function() {}
});