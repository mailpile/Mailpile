/* Modals - Tags */

Mailpile.UI.Modals.TagAdd = function(add_tag_data) {
  var add_tag_template = _.template($('#modal-add-tag').html());
  var add_tag_html = add_tag_template(add_tag_data);
  $('#modal-full').html(add_tag_html);

  // Show Modal
  $('#modal-full').modal(Mailpile.UI.ModalOptions);
};


Mailpile.UI.Modals.TagAddProcess = function(location) {
  var tag_data = $('#modal-form-tag-add').serialize();
  Mailpile.API.tags_add_post(tag_data, function(result) {

    // Template
    var tag_template = _.template($('#template-sidebar-item').html());

    if (result.status == 'success' && location == 'sidebar') {

      // Add Item
      var tag_html = tag_template(result.result.added[0]);
      $('#sidebar-tag').prepend(tag_html);

      // Add To Model
      Mailpile.instance.tags.push(result.result.added[0]);

      // Update UI things
      Mailpile.UI.Sidebar.Draggable('a.sidebar-tag');
      Mailpile.UI.Sidebar.Droppable('li.sidebar-tags-draggable', 'td.draggable');
      // FIXME: these drag & drops probably break on non search views
      $('#modal-full').modal('hide');

    } else {
      Mailpile.notification(result);
    }
  });  
};