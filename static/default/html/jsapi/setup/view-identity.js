// Setup View
var IdentityView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function() {
  },
  events: {
    "click #btn-setup-crypto-import"       : "processCryptoImport",
  	"click #btn-setup-source-settings"     : "processSourceSettings",
  	"click #btn-setup-source-local-import" : "processSourceImport"
  },
  showDiscovery: function() {
    this.$el.html(_.template($("#template-setup-discovery").html()));
    $('#demo-setup-discovery-action').delay(1500).fadeIn('normal');
  },
  showCryptoGenerated: function() {
    this.$el.html(_.template($('#template-setup-crypto-generated').html(), CryptoModel.attributes));
  },
  showSourceSettings: function() {
    this.$el.html(_.template($('#template-setup-source-local-settings').html(), SourceModel.attributes));      
  },
  showSourceLocal: function() {
    this.$el.html(_.template($('#template-setup-source-local').html(), SourceModel.attributes));      
  },
  showSourceRemoteChoose: function() {
    this.$el.html(_.template($('#template-setup-source-remote-choose').html(), {}));      
  },
  processCryptoImport: function(e) {
    alert('Prolly want to have to some "importing all the strong crypto maths feedback / progress thingy here before proceeding"');
    e.preventDefault();
    Backbone.history.navigate('#source-settings', true);
  }
});