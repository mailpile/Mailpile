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

  var baseMatcher = function(strs) {
    return function findMatches(q, cb) {
      var matches, substrRegex;
      matches = [];
      substrRegex = new RegExp(q, 'i');
      $.each(strs, function(i, str) {
        if (substrRegex.test(str.term)) {
          matches.push(str);
        }
      });
      cb(matches);
    };
  };

  var tagMatcher = function(strs) {
    return function findMatches(q, cb) {
      var matches, substrRegex;
      matches = [];
      substrRegex = new RegExp(q, 'i');
      $.each(strs, function(i, str) {
        if (substrRegex.test(str.name)) {
          matches.push(str);
        }
      });
      cb(matches);
    };
  };

  var peopleMatcher = function(strs) {
    return function findMatches(q, cb) {
      var matches, substrRegex;
      matches = [];
      substrRegex = new RegExp(q, 'i');
      $.each(strs, function(i, str) {
        if (substrRegex.test(str.fn) || substrRegex.test(str.address)) {
          str.term =  'from:';
          matches.push(str);
        }
      });
      cb(matches);
    };
  };

  // List of basic suggestions for search helpers
  var helpers = [
    { term: 'dates:', helper: '2011-12..2012-04-15' },
    { term: 'date:', helper: 'date:2013-8-3 +date:2013-9-10' },
    { term: 'year:', helper: '2013' },
    { term: 'month:', helper: '8' },
    { term: 'subject:', helper: 'any normal words' },
    { term: 'att:', helper: 'jpg' },
    { term: 'has:', helper: 'attachment' },
    { term: 'contacts: ', helper: 'name@email.com' },
    { term: 'to:', helper: 'name@email.com' }
  ];

  // Create Typeahead
  $('#form-search .typeahead').typeahead({
    hint: true,
    highlight: true,
    minLength: 0
  },{
    name: 'search',
    displayKey: 'term',
    source: baseMatcher(helpers),
    templates: {
      suggestion: function(data) {
        var template = _.template('<div class="tt-suggestion"><p><span class="icon-search"></span> <%= term %> <span class="helper"><%= helper %></span></p></div>');
        return template(data);
      }
    }
  },{
    name: 'tags',
    displayKey: function(value) {
      return 'in:' + value.slug
    },
    source: tagMatcher(Mailpile.instance.tags),
    templates: {
      empty: '<div class="tt-suggestion"><p><span class="icon-tag"></span> No tags match your search</p></div>',
      suggestion: function(data) {
        if (data.display !== 'invisible') {
          var template = _.template('<div class="tt-suggestion"><p><span class="color-<%= label_color %> <%= icon %>"></span> <%= name %></p></div>');
          return template(data);
        }
      }
    }
  },{
    name: 'people',
    displayKey: function(value) {
      return value.term + value.address;
    },
    source: peopleMatcher(Mailpile.instance.addresses),
    templates: {
      header: '<span class="separator"></span>',
      empty: '<div class="tt-suggestion"><p><span class="icon-user"></span> No people match your search</p></div>',
      suggestion: function(data) {
        if (data.photo === undefined) { data.photo = '/static/img/avatar-default.png'; }
        var template = _.template('<div class="tt-suggestion"><p><img class="avatar" src="<%= photo %>"> <%= term %> <%= fn %></p></div>');
        return template(data);
      }
    }
  },{
    name: 'keys',
    displayKey: 'term',
    source: baseMatcher([{ term: 'keys: team@mailpile.is' },{ term: 'keys: 707775F9' }]),
    templates: {
      suggestion: function(data) {
        var template = _.template('<div class="tt-suggestion"><p><span class="icon-key"></span> <%= term %></p></div>');
        return template(data);
      }
    }
  });

};