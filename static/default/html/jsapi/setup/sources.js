/* Setup - Sources - Model */
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


/* Setup - Sources - View */
var SourcesView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function() {
  },
  events: {
  	"click #btn-setup-source-settings"     : "processSourceSettings",
  	"click #btn-setup-source-local-import" : "processSourceImport"
  },
  showDiscovery: function() {
    this.$el.html(_.template($("#template-setup-discovery").html()));
    $('#demo-setup-discovery-action').delay(1500).fadeIn('normal');
  },
  showSourceSettings: function() {
    this.$el.html(_.template($('#template-setup-source-local-settings').html(), SourceModel.attributes));      
  },
  showSourceLocal: function() {
    this.$el.html(_.template($('#template-setup-source-local').html(), SourceModel.attributes));      
  },
  showSourceRemoteChoose: function() {
    this.$el.html(_.template($('#template-setup-source-remote-choose').html(), {}));      
  }
});