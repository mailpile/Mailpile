/* Pile */


  


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




	/* Bulk Actions */
	$(document).on('click', '.bulk-action', function(e) {

		e.preventDefault();
		var checkboxes = $('#pile-results input[type=checkbox]');
		var action = $(this).attr('href');
		var count = 0;

		$.each(checkboxes, function() {
			if ($(this).val() === 'selected') {
				console.log('This is here ' + $(this).attr('name'));
				count++;
			}
		});

		alert(count + ' items selected to "' + action.replace('#', '') + '"');
	});


	/* Result Actions */
	var pileActionSelect = function(item) {

    // Data Stuffs    
    mailpile.bulk_cache_add(item.data('mid'));

		// Increment Selected
		$('#bulk-actions-selected-count').html(parseInt($('#bulk-actions-selected-count').html()) + 1);

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

    // Data Stuffs    
    mailpile.bulk_cache_remove(item.data('mid'));

		// Decrement Selected
		var selected_count = parseInt($('#bulk-actions-selected-count').html()) - 1;

		$('#bulk-actions-selected-count').html(selected_count);

		// Hide Actions
		if (selected_count < 1) {
			$('#bulk-actions').slideUp('slow');
		}

		// Style & Unselect Checkbox
		item.removeClass('result-on').addClass('result')
		.data('state', 'normal')
		.find('td.checkbox input[type=checkbox]')
		.val('normal')
		.prop('checked', false);
	}


	$(document).on('click', '#pile-results tr', function(e) {
		if (e.target.href === undefined && $(this).data('state') === 'selected') {
			pileActionUnselect($(this));
		}
		else if (e.target.href === undefined) {
			pileActionSelect($(this));
		}
	});



  /* Dragging */
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
    }
  });



  /* Dropping */
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
  		  url			 : '/api/0/tag/',
  		  type		 : 'POST',
  		  data     : {
          add: $(this).data('tag_name'),
          del: getDelTag,
          mid: mailpile.bulk_cache
        },
  		  dataType : 'json',
  	    success  : function(response) {
          
          if (response.status == 'success') {
            $.each(mailpile.bulk_cache, function(key, mid) {
              $('#pile-message-' + mid).fadeOut('fast');
            });  
          } else {
            statusMessage(response.status, response.message);
          }
  	    }
  	  });  	  
    }
  });