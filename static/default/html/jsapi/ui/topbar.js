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
  	  $("#content-view").html(data.result);
    });
  }
  else if (search_query.substring(0, 9) === 'tags:') {
    console.log('trying to search for tags');
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
	Mailpile.API.message_compose_post({}, function(response) {
    if (response.status === 'success') {
      window.location.href = Mailpile.urls.message_draft + response.result.created[0] + '/';
    } else {
      Mailpile.notification(response.status, response.message);
    }
  });
});


/* Activities - DOM */
$(document).ready(function() {
  // Command Specific Mods
  if (Mailpile.instance.state.command_url == '/contacts/') {
    $('#search-query').val('contacts: ');
  }
});