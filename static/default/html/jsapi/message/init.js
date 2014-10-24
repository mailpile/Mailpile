/* Message - Create new instance of composer */

Mailpile.Message = {};
Mailpile.Message.Tooltips = {};

Mailpile.Message.init = function() {

  /* Drag & Drop */
  Mailpile.UI.Message.Draggable('div.thread-draggable');
  Mailpile.UI.Sidebar.Droppable('li.sidebar-tags-draggable', 'div.thread-draggable');


  Mailpile.UI.Message.ScrollToMessage();
  Mailpile.Message.Tooltips.Crypto();

};