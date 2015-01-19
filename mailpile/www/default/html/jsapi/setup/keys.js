/* Setup - Keys- View */
var KeysView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  events: {
    "click #btn-setup-keys-settings": "processKeys",
  },
  show: function() {
    $('#setup').html($('#template-setup-keys').html());
  },
  processKeys: function(e) {
    e.preventDefault();
    var keys_data = $('#form-setup-keys').serializeObject();
    Mailpile.API.setup_crypto_post(keys_data, function(result) {
      console.log(result);
    });
  }
});