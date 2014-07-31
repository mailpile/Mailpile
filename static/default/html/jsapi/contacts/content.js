/* Contacts - Show contact add form */
$(document).on('click', '.btn-activity-contact_add', function(e) {

  e.preventDefault();

  $('.sub-navigation ul li').removeClass('navigation-on');
  $(this).addClass('navigation-on');

  var modal_data = { name: '', address: '', extras: '' };
  var modal_html = $("#modal-contact-add").html();
  $('#modal-full').html(_.template(modal_html, modal_data));
  $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
});


/* Contact - Form -  */
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


/* Contact - Search keyserver */
$(document).on('click', '#contact-add-keysearch', function() {

  var query = $('.contact-add-name').val() + ' ' + $('.contact-add-email').val();
  Mailpile.find_encryption_keys(query);

});


/* Contacts - View Page */
function extractEmailFromLocation() {
  var pathname = decodeURIComponent(location.pathname);
  var parts = pathname.split('/').filter(function(el) {return el.length > 0})
  return parts[parts.length - 1]
}


$('.contact-key-use').on('change', function(e) {
  alert('This will update a KEYS USE state');
});


/* Contacts - Change the Crypto Policy associated with a contact */
$('#crypto-policy').on('change', function(e) {
    var policy = e.val
    var email = extractEmailFromLocation()
    var data = { email: email, policy: policy }

    $.ajax({
        url : '/api/0/crypto_policy/set/',
        type : 'POST',
        data : data,
        dataType : 'json'
    });
});


/* Contacts - Show details of a given key */
$('.show-key-details').on('click', function(e) {
  e.preventDefault();
  $(this).hide();
  var keyid = $(this).data('keyid');
  $('#contact-key-details-' + keyid).fadeIn();
});


$(document).ready(function() {

  // Hide Key Details
  $('.contact-key-details').hide();

});