Mailpile.go = function(url) {
  window.location.href = url;
};


Mailpile.bulk_cache_add = function(type, value) {
  if (_.indexOf(this[type], value) < 0) {
    this[type].push(value);
  }
};


Mailpile.bulk_cache_remove = function(type, value) {
  if (_.indexOf(this[type], value) > -1) {
    this[type] = _.without(this[type], value);
  }
};


$(document).on('click', '.checkbox-item-picker', function(e) {

	if (e.target.href === undefined && $(this).data('state') === 'selected') {
		console.log('Unselect tag: ' + $(this).data('tid') + ' ' + $(this).data('slug'));

    // Remove Cache
    mailpile.bulk_cache_remove('tags_cache', $(this).data('tid'));

		$(this).data('state', 'none').removeClass('checkbox-item-picker-selected').find('input[type=checkbox]').val('none').removeAttr('checked').prop('checked', false);
	}
	else if (e.target.href === undefined) {
		console.log('Select tag: ' + $(this).data('tid') + ' ' + $(this).data('slug'));

    // Add To Data Model
    mailpile.bulk_cache_add('tags_cache', $(this).data('tid'));

		$(this).data('state', 'selected').addClass('checkbox-item-picker-selected').find('input[type=checkbox]').val('selected').prop('checked', true);
	}
});


/* Compose - Create a new email to an address */
$(document).on('click', 'a', function(e) {
  if ($(this).attr('href').startsWith('mailto:')) {
    e.preventDefault();
    Mailpile.activities.compose($(this).attr('href').replace('mailto:', ''));
  }
});
