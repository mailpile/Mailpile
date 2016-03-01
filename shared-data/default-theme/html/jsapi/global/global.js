Mailpile.fix_url = function(url) {
  if (url.indexOf("{{ config.sys.http_path }}") != 0) {
    return "{{ config.sys.http_path }}" + url;
  }
  return url;
}

Mailpile.go = function(url) {
  Mailpile.notify_working(undefined, 1000);
  window.location.href = Mailpile.fix_url(url);
};


Mailpile.bulk_cache_human_length = function(type) {
  if (_.indexOf(this[type], '!all') < 0) return this[type].length;
  return '{{_("All")|escapejs}}';
};

Mailpile.bulk_cache_add = function(type, value) {
  if (_.indexOf(this[type], value) < 0) {
    this[type].push(value);
  }
};

Mailpile.bulk_cache_remove = function(type, value) {
  if (_.indexOf(this[type], value) > -1) {
    this[type] = _.without(this[type], value);
  }
  // Removing anything at all implies we not everything is selected
  if (_.indexOf(this[type], '!all') > -1) {
    this[type] = _.without(this[type], '!all');
  }
};


/* Compose - Create a new email to an address */
$(document).on('click', 'a', function(e) {
  if ($(this).attr('href') && ($(this).attr('href').indexOf('mailto:') == 0)) {
    e.preventDefault();
    Mailpile.activities.compose($(this).attr('href').replace('mailto:', ''));
  }
});
