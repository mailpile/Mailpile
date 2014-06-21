$(document).on('click', '#search-query', function() {
  $(this).select();  
});


$(document).on('click', '#button-search-options', function(key) {
	$('#search-params').slideDown('fast');
});


$(document).on('blur', '#button-search-options', function(key) {
	$('#search-params').slideUp('fast');
});