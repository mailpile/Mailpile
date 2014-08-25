/* Setup - State - Model */
var StateModel = Backbone.Model.extend({
  url: '/setup/as.json',
  defaults: {
    result: {
      language: false,
      crypto: false,
      profiles: false,
      routes: false,
      sources: false      
    }
  },
  checkState: function(view) {

    var state = '';
    var check = this.attributes.result;

    if (!check.language) {
      console.log('Needs Language');
      state = '/setup/welcome';
    }
    else if (!check.crypto) {
      console.log('Needs Crypto');
      state = '/setup/crypto/';
    }
    else if (!check.profiles) {
      console.log('Needs Profiles');
      state = '#profiles';
    }
    else if (check.profiles && view == '#profiles') {
      state = '#profiles';
    }
    else if (!check.routes) {
      console.log('Needs Routes');
      state = '#sending/add';
    }
    else if (check.routes && view == '#sending') {
      state = '#sending';
    }
    else if (!check.sources) {
      console.log('Needs Sources');
      state = '#sources/add';
    }
    else if (check.profiles && view == '#sources/add') {
      state = '#sources/add';
    }
    else if (check.sources && view == '#sources') {
      state = '#sources';
    }
    else if (check.language &&
             check.crypto &&
             check.profiles &&
             check.sending &&
             check.sources &&
             view == 'importing') {
      state = '#importing';
    }
    else {
      console.log('Just Go Home');
      state = '#';
    }

    // Redirect or Return
    if (state.indexOf('#') === -1) {
      window.href = state;
    } else {
      return state;
    }
  }
});