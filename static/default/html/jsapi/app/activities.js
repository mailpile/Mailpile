/* Activities */
Mailpile.activities.compose = function(address) {
  var compose_data = {};
  if (address) {
    compose_data = {to: address};
  }
	Mailpile.API.message_compose_post(compose_data, function(response) {
    if (response.status === 'success') {
      window.location.href = Mailpile.urls.message_draft + response.result.created[0] + '/';
    } else {
      Mailpile.notification(response);
    }
  });
};


Mailpile.activities.render_typeahead = function() {

  var substringMatcher = function(strs) {
    return function findMatches(q, cb) {
      var matches, substrRegex;
  
      // an array that will be populated with substring matches
      matches = [];
  
      // regex used to determine if a string contains the substring `q`
      substrRegex = new RegExp(q, 'i');
  
      // iterate through the pool of strings and for any string that
      // contains the substring `q`, add it to the `matches` array
      $.each(strs, function(i, str) {
        if (substrRegex.test(str)) {
          // the typeahead jQuery plugin expects suggestions to a
          // JavaScript object, refer to typeahead docs for more info
          matches.push({ value: str });
        }
      });
  
      cb(matches);
    };
  };

  // List of basic suggestions for search helpers
  var helpers = ['to: ', 'from: ', 'subject: ', 'in: ', 'contacts: ', 'tags: ', 'keys: '];

  $('#form-search .typeahead').typeahead({
    hint: true,
    highlight: true,
    minLength: 0
  },{
    name: 'helpers',
    displayKey: 'value',
    source: substringMatcher(helpers)
  });

};