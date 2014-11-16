/* Topbar - Search - Focus */
$(document).on('click', '#search-query', function() {
  $(this).select();
});


/* Search - Special handling of certain queries */
$(document).on('submit', '#form-search', function(e) {
  var search_query = $('#search-query').val();
  if (search_query.substring(0, 3) === 'in:') {
    var more_check = search_query.substring(3, 999).split(' ');
    if (!more_check[1]) {
      e.preventDefault();
      window.location.href = '/in/' + $.trim(search_query.substring(3, 999)) + '/';
    }
  }
  else if (search_query.substring(0, 9) === 'contacts:') {
    e.preventDefault();
    $.getJSON("/contacts/" + $.trim(search_query.substring(9, 999)) + "/as.jhtml", function(data) {
  	  $("#content-wide").html(data.result);
    });
  }
  else if (search_query.substring(0, 5) === 'tags:') {
    e.preventDefault();
    $.getJSON("/tags/" + $.trim(search_query.substring(5, 999)) + "/as.jhtml", function(data) {
  	  $("#content-wide").html(data.result);
    });
  }
  else if (search_query.substring(0, 5) === 'keys:') {
    e.preventDefault();
    Mailpile.UI.Modals.CryptoFindKeys({
      query: $.trim(search_query.substring(5, 999))
    });
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


/* Show Settings Dropdown */
$(document).on('mouseover', '#button-settings', function() {
  // FIXME: crap, this makes the links in the dropdown note fire... something obnoxious in Bootstrap causes it :(
  // $('#settings-menu').dropdown('toggle');
});



