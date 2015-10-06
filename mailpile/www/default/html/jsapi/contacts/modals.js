/* Modals - Contacts */

Mailpile.UI.Modals.ContactAdd = function() {
  $('.sub-navigation ul li').removeClass('navigation-on');
  $(this).addClass('navigation-on');

  Mailpile.API.with_template('modal-contact-add', function(modal) {
    var modal_data = { name: '', address: '', extras: '' };
    Mailpile.UI.show_modal(modal(modal_data));
  });
};


Mailpile.UI.Modals.ContactAddProcess = function() {
  Mailpile.API.contacts_add_post($('#form-contact-add').serialize(), function(result) {
    if (result.status == 'success') {
      $('#modal-full').modal('hide');

      // If Contacts List
      var $clist = $('#contacts-list');
      if ($clist.length > 0) {
        var contact_template = _.template($('#template-contact-list-item').html());
        var contact_html = contact_template(result.result.contact);
        $clist.append(contact_html);
      }
    }
  });
};
