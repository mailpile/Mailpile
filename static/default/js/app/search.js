/* Search */


	/* Hide Various Things */
	$('#search-params, #bulk-actions').hide();

	/* Search Box */
	$('#qbox').bind("focus", function(key) {
		$('#search-params').slideDown('fast');
	});

	$('#qbox').bind("blur", function(key) {
		$('#search-params').slideUp('fast');
	});

	for (item in keybindings) {
		if (item[1] == "global") {
			Mousetrap.bindGlobal(item[0], item[2]);
		} else {
			Mousetrap.bind(item[0], item[2]);
		}
	}