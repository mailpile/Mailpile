/* Pile */


  /* Filter New */
  $('.button-sub-navigation').on('click', function() {

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
	$('.bulk-action').on('click', function(e) {

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

	$('#pile-results').on('click', 'tr', function(e) {
		if (e.target.href === undefined && $(this).data('state') === 'selected') {
			pileActionUnselect($(this));
		}
		else if (e.target.href === undefined) {
			pileActionSelect($(this));
		}
	});


  /* Pile - Sorting of Messages */
  var pileActionTag = function(form_data) {

	  $.ajax({
		  url			 : '/api/0/tag',
		  type		 : 'POST',
		  data     : form_data,
		  dataType : 'json',
	    success  : function(response) {
        statusMessage(response.status, response.message);
//        if (response.status == 'success') {
          console.log(response);
//        }
	    }
	  });

  }



  /* Dragging */
  $('td.draggable').draggable({
    containment: "#container",
    scroll: false,
    revert: true,
    helper: function(event) {

      var selected_count = parseInt($('#bulk-actions-selected-count').html());

      console.log($(this).parent().data('tags'));
      
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

      var old_html = $(this).html();
      $(this).addClass('sidebar-tags-draggable-highlight').html('Moved :)');

      console.log();

      var form_data = {
        add: '',
        del: '',
        mid: ''
      };

    }
  });