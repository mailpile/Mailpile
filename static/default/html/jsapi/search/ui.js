MailPile.prototype.focus_search = function() {
	$("#search-query").focus(); return false;
};


/* Search - Action Select */
MailPile.prototype.pile_action_select = function(item) {

  // Add To Data Model
  mailpile.bulk_cache_add('messages_cache', item.data('mid'));

	// Update Bulk UI
  mailpile.bulk_actions_update_ui();

	// Style & Select Checkbox
	item.removeClass('result').addClass('result-on')
	.data('state', 'selected')
	.find('td.checkbox input[type=checkbox]')
	.val('selected')
	.prop('checked', true);
};


/* Search - Action Unselect */
MailPile.prototype.pile_action_unselect = function(item) {

  // Remove From Data Model
  mailpile.bulk_cache_remove('messages_cache', item.data('mid'));

	// Hide Actions
	mailpile.bulk_actions_update_ui();

	// Style & Unselect Checkbox
	item.removeClass('result-on').addClass('result')
	.data('state', 'normal')
	.find('td.checkbox input[type=checkbox]')
	.val('normal')
	.prop('checked', false);
};


/* Search - Result List */
MailPile.prototype.results_list = function() {

  // Navigation
	$('#btn-display-list').addClass('navigation-on');
	$('#btn-display-graph').removeClass('navigation-on');
	
	// Show & Hide View
	$('#pile-graph').hide('fast', function() {

    $('#form-pile-results').show('normal');
    $('#pile-results').show('fast');
    $('.pile-speed').show('normal');
    $('#footer').show('normal');
	});
};