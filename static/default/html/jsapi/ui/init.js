/* UI */

Mailpile.UI = {
  ModalOptions: { backdrop: true, keyboard: true, show: true, remote: false }
};


Mailpile.UI.init = function() {


  /* Make search items draggable to sidebar */
  $('li.sidebar-tags-draggable').droppable(Mailpile.sidebar_tags_droppable_opts);

};
