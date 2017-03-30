/* Tags */

Mailpile.Tags = {};
Mailpile.Tags.UI = {};
Mailpile.Tags.Tooltips = {};

Mailpile.Tags.init = function() {

  var tids = "" + $('#pile-results').data('tids');
  $("#sidebar li").removeClass('navigation-on');
  if (tids) {
    $.each(tids.split(/ /), function() {
      $("#sidebar li#sidebar-tag-" + this).addClass('navigation-on');
    });
  }

};

