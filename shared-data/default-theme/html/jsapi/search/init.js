/* Search */

Mailpile.Search = {};
Mailpile.Search.Tooltips = {};

Mailpile.Search.init = function() {

  // Drag Items
  var index_capabilities = $('.pile-results').data('index-capabilities');
  if (index_capabilities.indexOf('has_tags') >= 0) {
    Mailpile.UI.Search.Draggable('td.draggable, td.avatar');
    Mailpile.UI.Search.Droppable('.pile-results tr', 'a.sidebar-tag');
  };

  // Render Display Size
  if (!Mailpile.local_storage['view_size']) {
    Mailpile.local_storage['view_size'] = Mailpile.config.web.display_density;
  }

  Mailpile.pile_display(Mailpile.local_storage['view_size']);

  // Display Select
  $.each($('a.change-view-size'), function() {
    if ($(this).data('view_size') == Mailpile.local_storage['view_size']) {
      $(this).addClass('selected');
    }
  });

  // Navigation highlights
  $.each($('.display-refiner'), function() {
    if (document.location.href.endsWith($(this).find('a').attr('href'))) {
      $(this).addClass('navigation-on');
    }
    else {
      $(this).removeClass('navigation-on');
    };
  });

  // Tooltips
  Mailpile.Search.Tooltips.MessageTags();

  // Focus and scroll...
  $('.pile-results .pile-message .subject a').eq(0).focus();
  var hashIndex = document.location.href.indexOf('#');
  if (hashIndex != -1) {
    var target = document.location.href.substring(hashIndex+1);
    var $elem = $('#' + target + ', .' + target);
    var top_pos = $elem.eq(0).position().top;
    $elem.eq(0).focus();
    setTimeout(function() {
      $('#content-view, #content-tall-view').animate({ scrollTop: top_pos }, 150);
    }, 50);
  }

  EventLog.subscribe(".mail_source", function(ev) {
    // Cutesy animation, just for fun
    if ((ev.data && ev.data.copying && ev.data.copying.running) ||
        (ev.data && ev.data.rescan && ev.data.rescan.running)) {
      $("#logo-bluemail").fadeOut(2000);
      $("#logo-redmail").hide(2000);
      $("#logo-greenmail").hide(3000);
      $("#logo-bluemail").fadeIn(2000);
      $("#logo-greenmail").fadeIn(4000);
      $("#logo-redmail").fadeIn(6000);
    }
  }, 'mail-source-subscription');
};
