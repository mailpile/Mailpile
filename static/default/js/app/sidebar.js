$(document).ready(function() {

  // Drag Sort Tag Order
	$( ".sidebar-sortable" ).sortable({
		placeholder: "sidebar-tags-sortable",
    distance: 13,
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

});