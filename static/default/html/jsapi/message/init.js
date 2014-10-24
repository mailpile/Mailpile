/* Message - Create new instance of composer */

Mailpile.Message = {};


Mailpile.Message.init = function() {

  /* Drag & Drop */
  Mailpile.UI.Message.Draggable('div.thread-draggable');
  Mailpile.UI.Sidebar.Droppable('li.sidebar-tags-draggable', 'div.thread-draggable');


  Mailpile.thread_scroll_to_message();
  Mailpile.thread_initialize_tooltips();

};