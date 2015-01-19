/* Modals */


Mailpile.UI.Modals.Basic = function(options) {

  var modal_template = _.template($(options.template).html());
  $('#modal-full').html(modal_template(options));
  $('#modal-full').modal(Mailpile.UI.ModalOptions);

};