
$(document).ready(function() {

	/* Hide Various Things */
	$('#search-params, #bulk-actions').hide();

	/* Search Box */
	$('#button-search-options').on("click", function(key) {
		$('#search-params').slideDown('fast');
	});

	$('#button-search-options').on("blur", function(key) {
		$('#search-params').slideUp('fast');
	});

	for (item in keybindings) {
		if (item[1] == "global") {
			Mousetrap.bindGlobal(item[0], item[2]);
		} else {
			Mousetrap.bind(item[0], item[2]);
		}
	}
	
});
