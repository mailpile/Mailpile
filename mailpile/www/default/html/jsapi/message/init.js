/* Message - Create new instance of composer */

Mailpile.Message = {};
Mailpile.Message.Tooltips = {};

Mailpile.Message.init = function() {

  /* Drag & Drop */
  Mailpile.UI.Message.Draggable('div.thread-draggable');

  /* Scroll To */
  Mailpile.UI.Message.ScrollToMessage();

  /* Tooltips */
  Mailpile.Message.Tooltips.Crypto();
  Mailpile.Message.Tooltips.Attachments();

};
