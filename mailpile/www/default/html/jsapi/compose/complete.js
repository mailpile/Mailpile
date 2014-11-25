/* Compose - Complete */

Mailpile.Composer.Complete = function(mid) {
  window.location.href = Mailpile.urls.message_sent + mid + "/";
  // FIXME: make this ajaxy and nice transitions and such
  // $('#form-compose-' + mid).slideUp().remove();
};