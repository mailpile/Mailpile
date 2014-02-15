// Make console.log not crash JS browsers that don't support it
if (!window.console) window.console = { log: $.noop, group: $.noop, groupEnd: $.noop, info: $.noop, error: $.noop };

Number.prototype.pad = function(size) {
	// Unfortunate padding function....
	if(typeof(size) !== "number"){
    size = 2;
  }
	var s = String(this);
	while (s.length < size) s = "0" + s;
	return s;
}

function MailPile() {
  this.instance       = {};
	this.search_cache   = [];
	this.bulk_cache     = [];
	this.keybindings    = [];
	this.commands       = [];
	this.graphselected  = [];
	this.defaults       = {
  	view_size: "comfy"
	}
	this.api = {
    compose      : "/api/0/message/compose/",
    compose_send : "/api/0/message/update/send/",
    compose_save : "/api/0/message/update/",
    contacts     : "/api/0/search/address/",
    message      : "/api/0/message/=",
  	tag          : "/api/0/tag/",
  	tag_add      : "/api/0/tag/add/",
  	search_new   : "/api/0/search/?q=in%3Anew",
  	settings_add : "/api/0/settings/add/"
	}
	this.urls = {
  	message_draft : "/message/draft/=",
  	message_sent  : "/thread/="
	}
	this.plugins = [];
};

MailPile.prototype.bulk_cache_add = function(mid) {
  if (_.indexOf(this.bulk_cache, mid) < 0) {
    this.bulk_cache.push(mid);
  }
};

MailPile.prototype.bulk_cache_remove = function(mid) {
  if (_.indexOf(this.bulk_cache, mid) > -1) {
    this.bulk_cache = _.without(this.bulk_cache, mid);
  }
};

MailPile.prototype.show_bulk_actions = function(elements) {
  $.each(elements, function(){    
    $(this).css('visibility', 'visible');
  });
};

MailPile.prototype.hide_bulk_actions = function(elements) {
  $.each(elements, function(){    
    $(this).css('visibility', 'hidden');
  });
};

MailPile.prototype.get_new_messages = function(actions) {    
  $.ajax({
	  url			 : mailpile.api.search_new,
	  type		 : 'GET',
	  dataType : 'json',
    success  : function(response) {
      if (response.status == 'success') {
        actions(response);
      }
    }
  });
};

MailPile.prototype.render = function() {

  // Dynamic CSS Reiszing
  var dynamic_sizing = function() {

    var sidebar_height = $('#sidebar').height();

    // Is Tablet or Mobile
    if ($(window).width() < 1024) {
      var sidebar_width = 0;
    }
    else {
      var sidebar_width = 225;
    }

    var content_width  = $(window).width() - sidebar_width;
    var content_height = $(window).height() - 62;
    var content_tools_height = $('#content-tools').height();
    var fix_content_view_height = sidebar_height - content_tools_height;
  
    $('.sub-navigation').width(content_width);
    $('#thread-title').width(content_width);
  
    // Set Content View
    $('#content-view').css('height', fix_content_view_height).css('top', content_tools_height);

    var new_content_width = $(window).width() - sidebar_width;
    $('.sub-navigation, .bulk-actions').width(new_content_width);
  };

  dynamic_sizing();

  // Resize Elements on Drag
  window.onresize = function(event) {
    dynamic_sizing();
  };

  // Hide Mailboxes
  if ($('#sidebar-tag-outbox').find('span.sidebar-notification').html() === undefined) {
    $('#sidebar-tag-outbox').hide();
  }
};

var keybindings = [
	["/", 		"normal",	function() { $("#search-query").focus(); return false; }],
	["C", 		"normal",	function() { mailpile.compose(); }],
	["g i", 	"normal",	function() { mailpile.go("/Inbox/"); }],
	["g c", 	"normal",	function() { mailpile.go("/_/contact/list/"); }],
	["g n c", 	"normal",	function() { mailpile.go("/_/contact/add/"); }],
	["g n m",	"normal",	function() { mailpile.go("/_/compose/"); }],
	["g t",		"normal",	function() { $("#dialog_tag").show(); $("#dialog_tag_input").focus(); return false; }],
	["esc",		"global",	function() {
		$("#dialog_tag_input").blur();
		$("#qbox").blur();
    $("#dialog_tag").hide();
  }],
];

var mailpile = new MailPile();
var favicon = new Favico({animation:'popFade'});

// Non-exposed functions: www, setup
$(document).ready(function() {

  // Render
  mailpile.render();

});


