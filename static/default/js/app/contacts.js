MailPile.prototype.contact = function(msgids, tags) {}
MailPile.prototype.addcontact = function(tagname) {}

/* Show Contact Add Form */
$(document).on('click', '#button-contact-add', function(e) {

  e.preventDefault();
  $('#contacts-list').hide();
  $('#contact-add').show();

  $('.sub-navigation ul li').removeClass('navigation-on');
  $(this).parent().addClass('navigation-on');
});


var contactActionSelect = function(item) {

  // Data Stuffs    
  mailpile.bulk_cache_add();

	// Increment Selected
	$('#bulk-actions-selected-count').html(parseInt($('#bulk-actions-selected-count').html()) + 1);


	// Style & Select Checkbox
	item.removeClass('result').addClass('result-on').data('state', 'selected');
};


var contactActionUnselect = function(item) {

  // Data Stuffs    
  mailpile.bulk_cache_remove();

	// Decrement Selected
	var selected_count = parseInt($('#bulk-actions-selected-count').html()) - 1;

	$('#bulk-actions-selected-count').html(selected_count);

	// Hide Actions
	if (selected_count < 1) {

	}

	// Style & Unselect Checkbox
	item.removeClass('result-on').addClass('result').data('state', 'normal');
};


$(document).on('click', '#contacts-list div.boxy', function(e) {
	if (e.target.href === undefined && $(this).data('state') === 'selected') {
		contactActionUnselect($(this));
	}
	else if (e.target.href === undefined) {
		contactActionSelect($(this));
	}
});
