/* Message - Create new instance of composer */

Mailpile.Message = {};
Mailpile.Message.UI = {};


Mailpile.Message.init = function() {

  Mailpile.Message.UI.Draggable();

  Mailpile.thread_scroll_to_message();
  Mailpile.thread_initialize_tooltips();

};