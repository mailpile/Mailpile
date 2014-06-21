/* Search - select item via clicking */
$(document).on('click', '#pile-results tr.result', function(e) {
  console.log()
	if (e.target.href === undefined &&
      $(this).data('state') !== 'selected' &&
      $(e.target).hasClass('pile-message-tag-name') == false) {
		mailpile.pile_action_select($(this));		
	}
});


/* Search - unselect search item via clicking */
$(document).on('click', '#pile-results tr.result-on', function(e) {
	if (e.target.href === undefined &&
      $(this).data('state') === 'selected' && 
      $(e.target).hasClass('pile-message-tag-name') == false) {
		mailpile.pile_action_unselect($(this));
	}
});


/* Search - Delete Tag via Tooltip */
$(document).on('click', '.pile-tag-delete', function(e) {
  e.preventDefault();
  var tid = $(this).data('tid');
  var mid = $(this).data('mid');
  mailpile.tag_add_delete([], tid, mid, function(result) {
    $('#pile-message-tag-' + tid + '-' + mid).qtip('hide').remove();
  });
});


/* Search - Dragging items from search to sidebar */
$('td.draggable').draggable({
  containment: "#container",
  appendTo: 'body',
  cursor: 'move',
  scroll: false,
  revert: false,
  opacity: 1,
  helper: function(event) {
    // FIXME: the word 'message' needs to updated as per Issue #666 mwhuahahaha
    if (mailpile.messages_cache.length == 0) {
      drag_count = '1 message</div>';
    } else {
      drag_count = mailpile.messages_cache.length + ' messages';
    }
    return $('<div class="pile-results-drag ui-widget-header"><span class="icon-inbox"></span> Moving ' + drag_count + '</div>');
  },
  start: function(event, ui) {

    // Add Draggable MID
    mailpile.bulk_cache_add('messages_cache', $(event.target).parent().data('mid'));

    // Update Bulk UI
    mailpile.bulk_actions_update_ui();

  	// Style & Select Checkbox
  	$(event.target).parent().removeClass('result').addClass('result-on')
  	.data('state', 'selected')
  	.find('td.checkbox input[type=checkbox]')
  	.val('selected')
  	.prop('checked', true);
  },
  stop: function(event, ui) {}
});


/* Search - DOM is ready */
$(document).ready(function() {
  
  // Render Display Size
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