$(document).on('click', '.sidebar-tag-expand', function(e) {
  e.preventDefault();
  var tid = $(this).parent().data('tid');
  Mailpile.UI.Sidebar.SubtagsToggle(tid);
});


$(document).on('click', '.is-editing', function(e) {
  e.preventDefault();
});


$(document).on('click', '#button-sidebar-organize', function(e) {
  e.preventDefault();
  Mailpile.UI.Sidebar.OrganizeToggle();
});


$(document).on('click', '.sidebar-tag-archive', function(e) {
  e.preventDefault();
  Mailpile.UI.Sidebar.TagArchive();
});


$(document).on('click', '#button-sidebar-add', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.TagAdd({ location: 'sidebar' });
});


$(document).on('click', '#button-modal-add-tag', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.TagAddProcess($(this).data('location'));
});