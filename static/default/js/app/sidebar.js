$(document).on('click', '.icon-tags', function(e) {

  e.preventDefault();
  var tid = $(this).parent().parent().data('tid');

  if ($('#sidebar-subtag-' + tid).css('display') === 'none') {
    $('#sidebar-subtag-' + tid).show();
  }
  else {
    $('#sidebar-subtag-' + tid).hide();    
  }

});



$(document).ready(function() {


  // Drag Sort Tag Order
	$( ".sidebar-sortable" ).sortable({
		placeholder: "sidebar-tags-sortable",
    distance: 13,
    scroll: false,
    opacity: 0.8,
		stop: function(event, ui) {
     
      var get_order = function(index, base) {
        $elem = $('.sidebar-sortable li:nth-child(' + index + ')');
        if ($elem.length) {
          return $elem.data('display_order');
        }
        else {
          return base
        }        
      };

      var tid   = $(ui.item).data('tid');
			var index = $(ui.item).index();

      // Calculate new orders
      var previous  = get_order(index, 0);
      var next      = get_order((parseInt(index) + 2), 1000000);
      var new_order = (parseFloat(previous) + parseFloat(next)) / 2;

      // Prep Update Value
      var key = 'tags.' + tid + '.display_order';
      var setting = {};
      setting[key] = new_order;

      // Save Tag Order
      mailpile.tag_update(tid, setting, function() {

        // Update Current Element
        $(ui.item).attr('data-display_order', new_order).data('display_order', new_order);
      });
		}
	}).disableSelection();
  

  // Drag Tags to Search Messages
  $('a.sidebar-tag').draggable({
    containment: "#container",
    appendTo: 'body',
    cursor: 'move',
    scroll: false,
    revert: false,
    opacity: 1,
    helper: function(event) {      
      return $('<div class="sidebar-tag-drag ui-widget-header">' + $(this).html() + '</div>');
    }
  });

  $('#pile-results tr').droppable({
    accept: 'a.sidebar-tag',
    hoverClass: 'result-hover',
    tolerance: 'pointer',
    drop: function(event, ui) {
      mailpile.tag_add_delete(ui.draggable.data('tag_slug'), '', $(event.target).data('mid'), function() {
        // FIXME: needs to show tag icon (if not exist) and more data attributes on inserted tag
        $(event.target).find('td.subject span.item-tags').append('<span class="pile-message-tag">' + ui.draggable.data('tag_name') + '</span>');  
      });      
    }
  });

});