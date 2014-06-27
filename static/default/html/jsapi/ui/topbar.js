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
    console.log('inside of else');
  }

});


$(document).on('click', '#button-search-options', function(key) {
	$('#search-params').slideDown('fast');
});


$(document).on('blur', '#button-search-options', function(key) {
	$('#search-params').slideUp('fast');
});


$(document).ready(function() {

  // Command Specific Mods
  if (Mailpile.instance.state.command_url == '/contacts/') {
    $('#search-query').val('contacts: ');
  }

});