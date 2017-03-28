Mailpile.fix_url = function(url) {
  if (url.indexOf("{{ config.sys.http_path }}") != 0) {
    return "{{ config.sys.http_path }}" + url;
  }
  return url;
}


/* Compose - Create a new email to an address */
$(document).on('click', 'a', function(e) {
  if ($(this).attr('href') && ($(this).attr('href').indexOf('mailto:') == 0)) {
    e.preventDefault();
    Mailpile.activities.compose($(this).attr('href').replace('mailto:', ''));
  }
});
