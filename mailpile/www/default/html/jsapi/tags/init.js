/* Tags */

Mailpile.Tags = {};
Mailpile.Tags.UI = {};
Mailpile.Tags.Tooltips = {};


Mailpile.Tags.init = function() {

  // Search Bar
  $('#search-query').val('tags: ');

  // Slugify
  $('#data-tag-add-slug').slugify('#data-tag-add-tag');

  // Tooltips
  Mailpile.Tags.Tooltips.CardSubtags();

};