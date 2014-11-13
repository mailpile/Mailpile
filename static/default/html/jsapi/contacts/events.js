/* Contacts - Show contact add form */
$(document).on('click', '.btn-activity-contact_add', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.ContactAdd();
});


/* Contact - Form  */
$(document).on('submit', '#form-contact-add', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.ContactAddProcess();
});


/* Contacts - Show details of a given key */
$(document).on('click', '.show-key-details', function(e) {
  e.preventDefault();
  $(this).hide();
  var keyid = $(this).data('keyid');
  $('#contact-key-details-' + keyid).fadeIn();
});


