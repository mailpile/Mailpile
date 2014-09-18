/* Topbar - Search - Focus */
$(document).on('click', '#search-query', function() {
  $(this).select();
});


/* Search - Special handling of certain queries */
$(document).on('submit', '#form-search', function(e) {
  var search_query = $('#search-query').val();
  if (search_query.substring(0, 9) === 'contacts:') {
    e.preventDefault();
    $.getJSON("/contacts/" + search_query.substring(10, 999) + "/as.jhtml", function(data) {
  	  $("#content-wide").html(data.result);
    });
  }
  else if (search_query.substring(0, 5) === 'tags:') {
    e.preventDefault();
    $.getJSON("/tags/" + search_query.substring(6, 999) + "/as.jhtml", function(data) {
  	  $("#content-wide").html(data.result);
    });
  }
  else if (search_query.substring(0, 5) === 'keys:') {
    e.preventDefault();
    var query = search_query.substring(6, 999);
    Mailpile.find_encryption_keys(query);
  }
  else {
    console.log('inside of else, just a normal query');
  }
});


/* Activities - */
$(document).on('click', '#button-search-options', function(key) {
	$('#search-params').slideDown('fast');
});


/* Activities - */
$(document).on('blur', '#button-search-options', function(key) {
	$('#search-params').slideUp('fast');
});


/* Activities - Create New Blank Message */
$(document).on('click', '#button-compose', function(e) {
	e.preventDefault();
  Mailpile.activities.compose();
});


/* Activities - DOM */
$(document).ready(function() {
  // Command Specific Mods
  if (Mailpile.instance.state.command_url === '/contacts/') {
    $('#search-query').val('contacts: ');
  }
  else if (Mailpile.instance.state.command_url === '/tags/') {
    $('#search-query').val('tags: ');
  }

});