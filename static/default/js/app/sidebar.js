$(function() {

		$( ".sidebar-sortable" ).sortable({
			placeholder: "ui-state-highlight",
			stop: function(event, ui) {
  			
  			
  			console.log($(ui.item).attr('id'));
  			
			}
		});

		$( ".sidebar-sortable" ).disableSelection();
	
});