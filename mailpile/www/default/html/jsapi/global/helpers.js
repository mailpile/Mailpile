/* Helpers */

Mailpile.Helpers = [{
    slug: 'what-is-encryption-key', 
    title: '{{_("What is an Encryption Key")|escapejs}}',
    actions: false
},{
    slug: 'what-is-missing-key',
    title: '{{_("What is Missing Encryption Key")|escapejs}}',
    actions: ['hideable']
}];


$(document).on('click', '.btn-helper', function(e) {
  e.preventDefault();
  var helper = $(this).data('helper');
  var helper_data = _.findWhere(Mailpile.Helpers, {slug: helper});

  helper_data['content'] = $('#template-helper-' + helper).html();

  console.log(helper);
  console.log(helper_data);

  var modal_template = _.template($('#template-modal-helper').html());
  Mailpile.UI.show_modal(modal_template(helper_data));
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
