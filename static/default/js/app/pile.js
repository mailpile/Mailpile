/* Filter New */
$(document).on('click', '.button-sub-navigation', function() {

  var filter = $(this).data('filter');
  $('#sub-navigation ul.left li').removeClass('navigation-on');

  if (filter == 'in_new') {

    $('#display-new').addClass('navigation-on');
    $('tr').hide('fast', function() {
      $('tr.in_new').show('fast');
    });
  }
  else if (filter == 'in_later') {

    $('#display-later').addClass('navigation-on');
    $('tr').hide('fast', function() {
      $('tr.in_later').show('fast');
    });
  }
  else {

    $('#display-all').addClass('navigation-on');
    $('tr.result').show('fast');
  }

  return false;
});



/* Tag Add Ajax */
var pileAjaxTag = function(tag_add) {

  $.ajax({
	  url			 : mailpile.api.tag,
	  type		 : 'POST',
	  data     : {
      add: tag_add,
      mid: mailpile.bulk_cache
    },
	  dataType : 'json',
    success  : function(response) {

      if (response.status == 'success') {

        // Update Pile View
        $.each(mailpile.bulk_cache, function(key, mid) {
          $('#pile-message-' + mid).fadeOut('fast');
        });

        // Empty Bulk Cache
        mailpile.bulk_cache = [];

      } else {
        mailpile.notification(response.status, response.message);
      }
    }
  });
}


/* Bulk Action Link */
$(document).on('click', '.bulk-action', function(e) {

	e.preventDefault();
	var action = $(this).data('action');

	alert(mailpile.bulk_cache.length + ' items to ' + action);

  if (action == 'later' || action == 'archive' || action == 'trash') {
    pileAjaxTag(action);
  }
  else if (action == 'add-to-group') {
    
  }
  else if (action == 'assign-tags') {
    
  }
});


/* Result Actions */
var pileActionSelect = function(item) {

  // Add To Data Model
  mailpile.bulk_cache_add(item.data('mid'));

	// Increment Selected
	$('#bulk-actions-selected-count').html(mailpile.bulk_cache.length);

	// Show Actions
	$('#bulk-actions').slideDown('slow');

	// Style & Select Checkbox
	item.removeClass('result').addClass('result-on')
	.data('state', 'selected')
	.find('td.checkbox input[type=checkbox]')
	.val('selected')
	.prop('checked', true);
}

var pileActionUnselect = function(item) {

  // Remove From Data Model
  mailpile.bulk_cache_remove(item.data('mid'));

	// Decrement Selected
	$('#bulk-actions-selected-count').html(mailpile.bulk_cache.length);

	// Hide Actions
	if (mailpile.bulk_cache.length < 1) {
		$('#bulk-actions').slideUp('slow');
	}

	// Style & Unselect Checkbox
	item.removeClass('result-on').addClass('result')
	.data('state', 'normal')
	.find('td.checkbox input[type=checkbox]')
	.val('normal')
	.prop('checked', false);
}



/* Select & Unselect Pile Items */
$(document).on('click', '#pile-results tr.result', function(e) {
	if (e.target.href === undefined && $(this).data('state') !== 'selected') {
		pileActionSelect($(this));
	}
});

$(document).on('click', '#pile-results tr.result-on', function(e) {
	if (e.target.href === undefined && $(this).data('state') === 'selected') {
		pileActionUnselect($(this));
	}
});



/* Dragging & Dropping From Pile */
$('td.draggable').draggable({
  containment: "#container",
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
    console.log('done dragging things');
  }
});

$('li.sidebar-tags-draggable').droppable({
  accept: 'td.draggable',
  activeClass: 'sidebar-tags-draggable-hover',
  hoverClass: 'sidebar-tags-draggable-active',
  tolerance: 'pointer',
  drop: function(event, ui) {

    var getDelTag = function() {
      if ($.url.segment(0) === 'in') {
        return $.url.segment(1);
      }
      return '';
    }

    // Add MID to Cache
    mailpile.bulk_cache_add(ui.draggable.parent().data('mid'));

    // Fire at Willhelm
	  $.ajax({
		  url			 : mailpile.api.tag,
		  type		 : 'POST',
		  data     : {
        add: $(this).data('tag_name'),
        del: getDelTag,
        mid: mailpile.bulk_cache
      },
		  dataType : 'json',
	    success  : function(response) {

        if (response.status == 'success') {

          // Update Pile View
          $.each(mailpile.bulk_cache, function(key, mid) {
            $('#pile-message-' + mid).fadeOut('fast');
          });

          // Empty Bulk Cache
          mailpile.bulk_cache = [];

        } else {
          mailpile.notification(response.status, response.message);
        }
	    }
	  });
  }
});