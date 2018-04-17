/* Clear button */
Mailpile.UI.set_clear_state = function(queryBox){
  var $clearButton = $(queryBox).next('.clear-search');
  if (queryBox.value.length > 0) {
    $clearButton.show();
  }
  else {
    $clearButton.hide();
  }
};

$(function(){
  var queryBox = $('#search-query');
  if (queryBox.length) {
    Mailpile.UI.set_clear_state(queryBox[0]);
  }
});

Mailpile.UI.maybe_hide_search_box = function() {
  $('nav.topbar-nav ul li').removeClass('hide');
  $('div.topbar-logo-name').show().removeClass('hide');
  $('nav.topbar-nav ul li.nav-search').show().addClass('mobile-pt-inline');
  $('form#form-search').addClass('mobile-pt-hide');
  $('nav.topbar-nav ul li.nav-search-hide').addClass('hide');
};
$(document).on('click', '#nav-search-hide', Mailpile.UI.maybe_hide_search_box);
$(document).on('click', '#nav-search', function() {
  $('nav.topbar-nav ul li').addClass('hide');
  $('div.topbar-logo-name').hide().addClass('hide');
  $('nav.topbar-nav ul li.nav-search').removeClass('mobile-pt-inline').hide();
  $('form#form-search').removeClass('mobile-pt-hide');
  $('nav.topbar-nav ul li.nav-search-hide').removeClass('hide');
  $('#search-query').focus();
});

$(document).on('input change', '#search-query', function(e) {
  Mailpile.UI.set_clear_state(e.target);
});

$(document).on('click', '#form-search .clear-search', function(e) {
  var dflt = $('#search-query').data('q');
  if ($('#search-query').val() == dflt) {
    $('#search-query').val('').focus();
    $(e.target).hide();
  }
  else {
    $('#search-query').val(dflt).focus();
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
// #}
// #

Mailpile.UI.content_setup.push(function($content) {
  // FIXME: This will do silly things if we have multiple search results
  //        on a page at a time.
  var $st = $content.find('#search-terms');
  var search_terms = $st.data('q');
  if (search_terms) {
    var $sq = $('#search-query');
    $sq.val(search_terms);
    $sq.data('q', search_terms);
    $sq.data('context', $st.data('context'));
    Mailpile.UI.set_clear_state($sq[0]);
  }
});
