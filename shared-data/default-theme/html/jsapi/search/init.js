/* Search */

Mailpile.Search = {};
Mailpile.Search.Tooltips = {};

Mailpile.Search.init = function() {

  // Drag Items
  Mailpile.UI.Search.Draggable('td.draggable');
  Mailpile.UI.Search.Dropable('.pile-results tr', 'a.sidebar-tag');

  // Render Display Size
  if (!Mailpile.local_storage['view_size']) {
    Mailpile.local_storage['view_size'] = Mailpile.config.web.display_density;
  }

  Mailpile.pile_display(Mailpile.local_storage['view_size']);

  // Display Select
  $.each($('a.change-view-size'), function() {
    if ($(this).data('view_size') == Mailpile.local_storage['view_size']) {
      $(this).addClass('view-size-selected');
    }
  });

  // Tooltips
  Mailpile.Search.Tooltips.MessageTags();

  EventLog.subscribe(".mail_source", function(ev) {
    // bre: re-enabling this just for fun and to test the event subscription
    //      code. This is broken in that it fails for non-English languages.
    if (ev.message.indexOf("Rescanning:") != -1) {
      $("#logo-bluemail").fadeOut(2000);
      $("#logo-redmail").hide(2000);
      $("#logo-greenmail").hide(3000);
      $("#logo-bluemail").fadeIn(2000);
      $("#logo-greenmail").fadeIn(4000);
      $("#logo-redmail").fadeIn(6000);
    }
    $('.status-in-title').attr('title', ev.data.name + ': ' + ev.message);
  });
};
