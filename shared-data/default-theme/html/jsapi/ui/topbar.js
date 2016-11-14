/* Topbar - Search - Focus */
$(document).on('focus', '#search-query', function() {
  $(this).select();
});


Mailpile.UI.content_setup.push(function($content) {
  var $sq = $('#search-query');
  if (($sq.data('q') == $sq.val()) || ($sq.val() == "")) {
    // FIXME: This will do silly things if we have multiple search results
    //        on a page at a time.
    var $st = $content.find('#search-terms');
    var search_terms = $st.data('q');
    if (search_terms !== undefined) {
      $sq.data('q', search_terms).val(search_terms)
         .data('context', $st.data('context'));
    }
  }
});


// {# FIXME: Disabled by Bjarni, this doesn't really work reliably
//  #
/* Search - Special handling of certain queries */
$(document).on('submit', '#form-search', function(e) {
  var search_query = $('#search-query').val();
  if (search_query.substring(0, 3) === 'in:') {
    var more_check = search_query.substring(3, 999).split(' ');
    if (!more_check[1]) {
      e.preventDefault();
      Mailpile.go('/in/' + $.trim(search_query.substring(3, 999)) + '/');
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
    $.getJSON("{{ config.sys.http_path }}/tags/" + $.trim(search_query.substring(5, 999)) + "/as.jhtml", function(data) {
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
// #
// #
// #}


/* Activities - Create New Blank Message */
$(document).on('click', '.button-compose', function(e) {
	e.preventDefault();
  Mailpile.activities.compose($(this).data('to'), $(this).data('from'));
});
