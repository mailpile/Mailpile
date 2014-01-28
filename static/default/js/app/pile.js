/* Pile - Action Select */
MailPile.prototype.pile_action_select = function(item) {

  // Add To Data Model
  mailpile.bulk_cache_add(item.data('mid'));

	// Increment Selected
	$('#bulk-actions-selected-count').html(mailpile.bulk_cache.length);

	// Style & Select Checkbox
	item.removeClass('result').addClass('result-on')
	.data('state', 'selected')
	.find('td.checkbox input[type=checkbox]')
	.val('selected')
	.prop('checked', true);
};


/* Pile - Action Unselect */
MailPile.prototype.pile_action_unselect = function(item) {

  // Remove From Data Model
  mailpile.bulk_cache_remove(item.data('mid'));

	// Decrement Selected
	$('#bulk-actions-selected-count').html(mailpile.bulk_cache.length);

	// Hide Actions
	if (mailpile.bulk_cache.length < 1) {

	}

	// Style & Unselect Checkbox
	item.removeClass('result-on').addClass('result')
	.data('state', 'normal')
	.find('td.checkbox input[type=checkbox]')
	.val('normal')
	.prop('checked', false);
};

/* Pile - Display */
MailPile.prototype.pile_display = function(current, change) {

  if (change) {
    $('#sidebar').removeClass(current).addClass(change);
    $('#pile-results').removeClass(current).addClass(change);
  } else {
    $('#sidebar').addClass(current);
    $('#pile-results').addClass(current);
  }
  
  setTimeout(function() {

    $('#sidebar').fadeIn('fast');
    $('#pile-results').fadeIn('fast');
  }, 250);
  
}

/* Pile - Bulk Select / Unselect All */
$(document).on('click', '#pile-select-all-action', function(e) {

  var checkboxes = $('#pile-results input[type=checkbox]');

  if ($(this).attr('checked') === undefined) {

    $.each(checkboxes, function() {      
      mailpile.pile_action_select($(this).parent().parent());
    });

    $(this).attr('checked','checked');

  } else {

    $.each(checkboxes, function() {
      mailpile.pile_action_unselect($(this).parent().parent());
    });

    $(this).removeAttr('checked');
  }
});

/* Pile - Bulk Action Link */
$(document).on('click', '.bulk-action', function(e) {

	e.preventDefault();
	var action = $(this).data('action');

//	alert(mailpile.bulk_cache.length + ' items to ' + action);

  if (action == 'later' || action == 'archive' || action == 'trash') {

    var delete_tag = '';

    if ($.url.segment(0) === 'in') {
     delete_tag = $.url.segment(1);
    }

    // Add / Delete
    mailpile.tag_add_delete(action, delete_tag, mailpile.bulk_cache, function() {

      // Update Pile View
      $.each(mailpile.bulk_cache, function(key, mid) {
        $('#pile-message-' + mid).fadeOut('fast');
      });

      // Empty Bulk Cache
      mailpile.bulk_cache = [];
    });   
  }
  else if (action == 'add-to-group') {
    
    // Open Modal or dropdown with options
  }
  else if (action == 'assign-tags') {

    // Open Modal with selection options
  }
});


/* Pile - Select & Unselect Items */
$(document).on('click', '#pile-results tr.result', function(e) {
	if (e.target.href === undefined && $(this).data('state') !== 'selected') {
		mailpile.pile_action_select($(this));
		console.log($(this));
		
	}
});

$(document).on('click', '#pile-results tr.result-on', function(e) {
	if (e.target.href === undefined && $(this).data('state') === 'selected') {
		mailpile.pile_action_unselect($(this));
	}
});


/* Pile - Change Display Size */
$(document).on('click', 'a.change-view-size', function(e) {

  e.preventDefault();
  var current_size = localStorage.getItem('view_size');
  var change_size = $(this).data('view_size');

  // Update Link Selected
  $('a.change-view-size').removeClass('view-size-selected');
  $(this).addClass('view-size-selected');

  // Update View Sizes
  mailpile.pile_display(current_size, change_size);

  // Data
  localStorage.setItem('view_size', change_size);
});


/* Dragging & Dropping From Pile */
$('td.draggable').draggable({
  containment: "#container",
  appendTo: 'body',
  scroll: false,
  revert: true,
  helper: function(event) {

    var selected_count = parseInt($('#bulk-actions-selected-count').html());

    if (selected_count == 0) {
      drag_count = '1 message</div>';
    }
    else {
      drag_count = selected_count + ' messages';
    }

    return $('<div class="pile-results-drag ui-widget-header"><span class="icon-message"></span> Move ' + drag_count + '</div>');
  },
  stop: function(event, ui) {
    //console.log('done dragging things');
  }
});


$('li.sidebar-tags-draggable').droppable({
  accept: 'td.draggable',
  activeClass: 'sidebar-tags-draggable-hover',
  hoverClass: 'sidebar-tags-draggable-active',
  tolerance: 'pointer',
  drop: function(event, ui) {

    var delete_tag = '';

    if ($.url.segment(0) === 'in') {
     delete_tag = $.url.segment(1);
    }

    // Add MID to Cache
    mailpile.bulk_cache_add(ui.draggable.parent().data('mid'));

    // Add / Delete
    mailpile.tag_add_delete($(this).data('tag_name'), delete_tag, mailpile.bulk_cache, function() {

      // Update Pile View
      $.each(mailpile.bulk_cache, function(key, mid) {
        $('#pile-message-' + mid).fadeOut('fast');
      });

      // Empty Bulk Cache
      mailpile.bulk_cache = [];
    });
  }
});


$(document).ready(function() {

  if (!localStorage.getItem('view_size')) {
    localStorage.setItem('view_size', mailpile.defaults.view_size);
  }

  mailpile.pile_display(localStorage.getItem('view_size'));

  // Display Select
  $.each($('a.change-view-size'), function() {
    if ($(this).data('view_size') == localStorage.getItem('view_size')) {
      $(this).addClass('view-size-selected');
    }
  });

});