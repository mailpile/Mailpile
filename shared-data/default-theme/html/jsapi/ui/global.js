Mailpile.render = function() {
  // DISABLED: Resize Elements Start + On Drag
  //Mailpile.render_dynamic_sizing();
  //window.onresize = function(event) {
  //  Mailpile.render_dynamic_sizing();
  //};

  // Show Mailboxes
  if ($('#sidebar-tag-outbox').find('span.sidebar-notification').html() !== undefined) {
    $('#sidebar-tag-outbox').show();
  }

{% if config.web.keybindings %}
  // Initialize/Configure Keybindings
  Mailpile.initialize_keybindings();
{% endif %}

  // Update page title from content, if necessary
  var $page_title_data = $('.page-title-data');
  var $page_title_icon = $page_title_data.find('.page-title-icon');
  var $page_title_text = $page_title_data.find('.page-title-text');
  if ($page_title_icon.length == 1) {
    $page_title_icon.clone().appendTo($('#page-title-icon').html(''));
    $('.topbar-logo a').addClass('mobile-hide');
    $('#page-title-icon').removeClass('mobile-hide').addClass('mobile-block');
  }
  else {
    $('.topbar-logo a').removeClass('mobile-hide');
    $('#page-title-icon').addClass('mobile-hide').removeClass('mobile-block');
  }
  if ($page_title_text.length == 1) {
    Mailpile.update_title($page_title_text.html());
    $page_title_text.clone().appendTo($('#page-title-text').html(''));
    $('#page-title-text').removeClass('mobile-hide');
    $('.topbar-logo-name a').addClass('mobile-hide');
  }
  else {
    $('.topbar-logo-name a').removeClass('mobile-hide');
    $('#page-title-text').addClass('mobile-hide').html('');
  };

  // This fixes some of the drag-drop misbehaviours; first we disable the
  // native HTML5 drag-drop of <a> elements...
  $('.pile-message a').on('dragstart', function(ev) {return false;});
};


Mailpile.update_title = function(message) {
  var ct = document.title;
  suffix = ct.substring(ct.indexOf('|'));
  document.title = message.replace(/&amp;/, '&') + ' ' + suffix;
};


Mailpile.render_dynamic_sizing = function() {
  var sidebar_width  = $('#sidebar').width();
  var content_width  = $(window).width() - sidebar_width;
  var content_height = $(window).height() - 62;
  if (content_width < 10) {
    /* This means we are in portrait mode */
    sidebar_width = 0;
    content_width = $(window).width();
    content_height -= 80;
  }
  var content_tools_height    = $('#content-tools').height();
  var new_content_width       = $(window).width() - sidebar_width;
  var new_content_view_height = content_height - content_tools_height;

  $('#content-tools').css('position', 'fixed');
  $('.sub-navigation').width(content_width);
  $('#thread-title').width(content_width);

  // Set Content View
  $('#content, #content-wide').css({'height': content_height});
  $('#content-tools, .sub-navigation, .bulk-actions').width(new_content_width);
  $('#content-view').css({'height': new_content_view_height, 'top': content_tools_height});
};


/* Mailpile - UI - Make fingerprints nicer */
Mailpile.nice_fingerprint = function(fingerprint) {
  // FIXME: I'd really love to make these individual pieces color coded
  // Pertaining to the hex value pairings & even perhaps toggle-able icons
  return fingerprint.split(/(....)/).join(' ');
};
