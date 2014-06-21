/* Activities */



/* Compose - Create New Blank Message */
$(document).on('click', '#button-compose', function(e) {
	e.preventDefault();
	mailpile.compose();
});