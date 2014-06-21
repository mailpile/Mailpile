MailPile.prototype.go = function(url) {
  window.location.href = url;
};


MailPile.prototype.bulk_cache_add = function(type, value) {
  if (_.indexOf(this[type], value) < 0) {
    this[type].push(value);
  }
};


MailPile.prototype.bulk_cache_remove = function(type, value) {
  if (_.indexOf(this[type], value) > -1) {
    this[type] = _.without(this[type], value);
  }
};


MailPile.prototype.command = function(command, data, method, callback) {
  if (method != "GET" && method != "POST") {
    method = "GET";
  }
  $.ajax({
    url      : command,
    type     : method,
    dataType : 'json',
    success  : callback,
  });
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