/* Tags */
// SPDX-FileCopyrightText: 2011-2015  Bjarni R. Einarsson, Mailpile ehf and friends
// SPDX-License-Identifier: AGPL-3.0-or-later


Mailpile.Tags = {};
Mailpile.Tags.UI = {};
Mailpile.Tags.Tooltips = {};

Mailpile.Tags.init = function() {

  var tids = ($('#pile-results').data('tids') || "") + "";
  $("#sidebar li").removeClass('navigation-on');
  if (tids) {
    $.each(tids.split(/ /), function() {
      $("#sidebar li#sidebar-tag-" + this).addClass('navigation-on');
    });
  }

};

