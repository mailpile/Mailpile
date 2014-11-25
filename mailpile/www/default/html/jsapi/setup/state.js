/* Setup - State - Model */
var StateModel = Backbone.Model.extend({
  url: '/api/0/setup/',
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
      state = '/setup/welcome/';
    }
    else if (!check.crypto) {
      state = '/setup/crypto/';
    }
    else if (!check.profiles) {
      state = '#profiles';
    }
    else if (check.profiles && view == '#profiles') {
      state = '#profiles';
    }
    else if (check.crypto && view == '#profiles/add') {
      state = '#profiles/add';
    }
    else if (!check.routes) {
      state = '#sending';
    }
    else if (check.routes && view == '#sending') {
      state = '#sending';
    }
    else if (check.profiles && view == '#sources/add') {
      state = '#sources/add';
    }
    else if (check.sources && view == '#sources') {
      state = '#sources';
    }
    else if (!check.sources) {
      state = '#sources';
    }
    else if (check.complete && view == '#complete') {
      state = '#complete';
    }
    else if (check.language &&
             check.crypto &&
             check.profiles &&
             check.routes &&
             check.sources &&
             view == '#complete') {
      state = '#complete';
    }
    else if (check.complete && view == '#') {
      state = '#';
    }
    else {
      state = '#error';
    }

    // Redirect or Return
    if (state.indexOf('#') === -1) {
      window.href = state;
    } else {
      return state;
    }
  }
});
