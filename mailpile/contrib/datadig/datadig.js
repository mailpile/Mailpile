// Display the datadig widget!
$(document).on('click', '.bulk-action-datadig', function() {
  Mailpile.API.with_template('datadig-modal', function(modal) {
    var options = {};
    $('#modal-full').html(modal(options));
    $('#modal-full').modal(Mailpile.UI.ModalOptions);
  });
});

return {}
