/* Search - select item via clicking */
$(document).on('click', '#pile-results tr.result', function(e) {
  console.log()
	if (e.target.href === undefined &&
      $(this).data('state') !== 'selected' &&
      $(e.target).hasClass('pile-message-tag-name') == false) {
		Mailpile.pile_action_select($(this));		
	}
});


/* Search - unselect search item via clicking */
$(document).on('click', '#pile-results tr.result-on', function(e) {
	if (e.target.href === undefined &&
      $(this).data('state') === 'selected' && 
      $(e.target).hasClass('pile-message-tag-name') == false) {
		Mailpile.pile_action_unselect($(this));
	}
});


/* Search - Delete Tag via Tooltip */
$(document).on('click', '.pile-tag-delete', function(e) {
  e.preventDefault();
  var tid = $(this).data('tid');
  var mid = $(this).data('mid');
  Mailpile.API.tag_post({ del: tid, mid: mid }, function(result) {
    Mailpile.notification(result);
    $('#pile-message-tag-' + tid + '-' + mid).qtip('hide').remove();
  });
});


/* Search - Searches web for people (currently keyservers only) */
$(document).on('click', '#btn-pile-empty-search-web', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.CryptoFindKeys({query: $('#pile-empty-search-terms').html() });
});

