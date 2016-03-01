/* Message - Create new instance of composer */

Mailpile.Message = {};
Mailpile.Message.Tooltips = {};

Mailpile.Message.setup = function($content) {
  /* Drag & Drop */
  Mailpile.UI.Message.Draggable($content.find('div.thread-draggable'));

  /* Tooltips */
  Mailpile.Message.Tooltips.Crypto($content);
  Mailpile.Message.Tooltips.Attachments($content);
};

Mailpile.Message.init = function() {
  /* Scroll To */
  Mailpile.UI.Message.ScrollToMessage();
};

Mailpile.UI.content_setup.push(Mailpile.Message.setup);
