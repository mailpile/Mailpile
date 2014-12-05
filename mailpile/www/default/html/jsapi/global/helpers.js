/* Helpers */

Mailpile.Helpers = [{
    slug: 'what-is-encryption-key', 
    title: '{{_("What is an Encryption Key")}}',
    actions: false
},{
    slug: 'what-is-missing-key',
    title: '{{_("What is Missing Encryption Key")}}',
    actions: ['hideable']
}];


$(document).on('click', '.btn-helper', function(e) {
  e.preventDefault();
  var helper = $(this).data('helper');
  var helper_data = _.findWhere(Mailpile.Helpers, {slug: helper});

  helper_data['content'] = $('#template-helper-' + helper).html();

  console.log(helper);
  console.log(helper_data);

  // Load Helper Specific HTML in Modal
  var modal_template = _.template($('#template-modal-helper').html());
  $('#modal-full').html(modal_template(helper_data));

  // Launch Modal
  $('#modal-full').modal(Mailpile.UI.ModalOptions);
});


$(document).on('click', '.btn-helper-action', function(e) {
  e.preventDefault();
  var action = $(this).data('action');

  console.log(action);

  // 
  $('#modal-full').modal('hide');

  // Show New  
  setTimeout(function() {
    Mailpile.UI.Modals[action]();
  }, 500);

});