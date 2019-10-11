Mailpile.fix_url = function(url) {
  if (url.indexOf("{{ config.sys.http_path }}") != 0) {
    return "{{ config.sys.http_path }}" + url;
  }
  return url;
}

Mailpile.go = function(url) {
  // FIXME: This check is lame; a workaround for the fact that download
  // URLs never end up triggering the event that cancels the notification.
  if (url.indexOf('/download/') < 0) {
    Mailpile.notify_working(undefined, 1000, 'blank');
  }
  window.location.href = Mailpile.fix_url(url);
};


/* Compose - Create a new email to an address */
$(document).on('click', 'a', function(e) {
  if ($(this).attr('href') && ($(this).attr('href').indexOf('mailto:') == 0)) {
    e.preventDefault();
    Mailpile.activities.compose($(this).attr('href').replace('mailto:', ''));
  }
});
