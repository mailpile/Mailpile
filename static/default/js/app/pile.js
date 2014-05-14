/* Pile - Action Select */
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


/* Pile - Action Unselect */
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


/* Pile - Select & Unselect Items */
$(document).on('click', '#pile-results tr.result', function(e) {
	if (e.target.href === undefined && $(this).data('state') !== 'selected') {
		mailpile.pile_action_select($(this));		
	}
});

$(document).on('click', '#pile-results tr.result-on', function(e) {
	if (e.target.href === undefined && $(this).data('state') === 'selected') {
		mailpile.pile_action_unselect($(this));
	}
});

/* Pile - Show Unread */
$(document).on('click', '.button-sub-navigation', function() {

  var filter = $(this).data('filter');

  $('.sub-navigation ul li').removeClass('navigation-on');
  $(this).parent().addClass('navigation-on');

  if (filter == 'in_unread') {

    $('#display-unread').addClass('navigation-on');
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


$(document).on('submit', '#form-tag-picker', function(e) {

  e.preventDefault();
  var action = $("button:focus").data('action');

  var add_tags = []
  var remove_tags = []
  if (action == 'add') { 
    add_tags = mailpile.tags_cache;
  }
  else if (action === 'remove') {
    remove_tags = mailpile.tags_cache
  }

  // Send Result
   mailpile.tag_add_delete(add_tags, remove_tags, mailpile.messages_cache, function(result) {
    var tag_link_template = $('#template-search-pile-tags-link').html();

    $.each(result.msg_ids, function(key, mid) {

      // Assign selector to minimize load on traversing DOM
      $item = $('#pile-message-' + mid + ' td.subject span.item-tags'); 

      // Add Icon
      if ($item.find('span.icon-tag').length < 1) {
        $item.html('<span class="icon-tag"></span>');
      }

      // Add Tags
      $.each(result.tagged, function(key, tag) {
        tag.mid = mid;
        $item.append(_.template(tag_link_template, tag));
      });

      // Remove Tags
      $.each(result.untagged, function(key, untag) {
        console.log('performing UNTAG on: ' + untag);
 //       if ($('#pile-message-tag-' + mid + '-' + tid).length) {
 //         $('#pile-message-tag-' + mid + '-' + tid).remove();
 //       };
      });      

    });

    // Clean Caches and hide Modal
    mailpile.messages_cache = [];
    mailpile.tags_cache = [];
    $('#modal-full').modal('hide');
  });

});


/* Dragging & Dropping From Pile */
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
    return $('<div class="pile-results-drag ui-widget-header"><span class="icon-message"></span> Moving ' + drag_count + '</div>');
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
  stop: function(event, ui) {
    
  }
});


$('li.sidebar-tags-draggable').droppable({
  accept: 'td.draggable',
  activeClass: 'sidebar-tags-draggable-hover',
  hoverClass: 'sidebar-tags-draggable-active',
  tolerance: 'pointer',
  over: function(event, ui) {
    mailpile.ui_sidebar_toggle_subtags($(this).find('a').data('tid'), 'open');
  },
  out: function(event, ui) {
    var tid = $(this).find('a').data('tid');
    mailpile.ui_sidebar_toggle_subtags($(this).find('a').data('tid'), 'close');
  },
  drop: function(event, ui) {

    // Add MID to Cache
    mailpile.bulk_cache_add('messages_cache', ui.draggable.parent().data('mid'));

    // Add / Delete
    mailpile.tag_add_delete($(this).find('a').data('tid'), mailpile.instance.search_tag_ids, mailpile.messages_cache, function() {

      // Update Pile View
      $.each(mailpile.messages_cache, function(key, mid) {
        $('#pile-message-' + mid).fadeOut('fast');
      });

      // Empty Bulk Cache
      mailpile.messages_cache = [];

      // Update Bulk UI
      mailpile.bulk_actions_update_ui();
    });
  }
});


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

  
  $('.pile-message-tag').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var tag = _.findWhere(mailpile.instance.tags, { tid: $(this).data('tid').toString() });              
        var template = $('#tooltip-pile-tag-details').html();
        var html = _.template(template, tag);
        return html;
      }
    },
    style: {
      classes: 'qtip-thread-crypto',
      tip: {
        corner: 'bottom center',
        mimic: 'bottom center',
        border: 0,
        width: 10,
        height: 10
      }
    },
    position: {
      my: 'bottom center',
      at: 'top left',
			viewport: $(window),
			adjust: {
				x: 7,  y: -4
			}
    },
    show: {
      delay: 150
    },
    hide: {
      delay: 1000
    }
  });

});