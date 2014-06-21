/* Search - Display Mode */
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
};


/* Search - Change Display Size */
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