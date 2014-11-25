Mailpile.render = function() {

  // Dynamic CSS Reiszing
  var dynamic_sizing = function() {

    // Is Tablet or Mobile
    if ($('#sidebar').length === 0 || $(window).width() < 1024) {
      var sidebar_width  = 0;
    }
    else {
      var sidebar_width  = 225;
    }

    var content_width  = $(window).width() - sidebar_width;
    var content_height = $(window).height() - 62;
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


  // Resize Elements Start + On Drag
  dynamic_sizing();
  window.onresize = function(event) {
    dynamic_sizing();
  };


  // Show Mailboxes
  if ($('#sidebar-tag-outbox').find('span.sidebar-notification').html() !== undefined) {
    $('#sidebar-tag-outbox').show();
  }

  // Mousetrap Keybindings
	for (item in Mailpile.keybindings) {
	  var keybinding = Mailpile.keybindings[item];
		if (keybinding[0] == "global") {
			Mousetrap.bindGlobal(keybinding[1], keybinding[2]);
		} else {
      Mousetrap.bind(keybinding[1], keybinding[2]);
		}
	}
};


/* Mailpile - UI - Make fingerprints nicer */
Mailpile.nice_fingerprint = function(fingerprint) {
  // FIXME: I'd really love to make these individual pieces color coded
  // Pertaining to the hex value pairings & even perhaps toggle-able icons
  return fingerprint.split(/(....)/).join(' ');
};