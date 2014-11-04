/* Contacts - Show contact add form */
$(document).on('click', '.btn-activity-contact_add', function(e) {

  e.preventDefault();

  $('.sub-navigation ul li').removeClass('navigation-on');
  $(this).addClass('navigation-on');

  var modal_data = { name: '', address: '', extras: '' };
  var modal_template = _.template($("#modal-contact-add").html());
  $('#modal-full').html(modal_template(modal_data));
  $('#modal-full').modal(Mailpile.UI.ModalOptions);
});


/* Contact - Form  */
$(document).on('submit', '#form-contact-add', function(e) {
  e.preventDefault();
  Mailpile.API.contacts_add_post($('#form-contact-add').serialize(), function(result) {
    if (result.status == 'success') {
      $('#modal-full').modal('hide');
      // FIXME: Will currenlty hide all instances of button
      $('.message-action-add-contact').hide();
    }
  });
});


/* Contacts - Show details of a given key */
$(document).on('click', '.show-key-details', function(e) {
  e.preventDefault();
  $(this).hide();
  var keyid = $(this).data('keyid');
  $('#contact-key-details-' + keyid).fadeIn();
});

