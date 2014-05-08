// Make console.log not crash JS browsers that don't support it
if (!window.console) window.console = { log: $.noop, group: $.noop, groupEnd: $.noop, info: $.noop, error: $.noop };

function MailPile() {
  this.instance       = {};
	this.search_cache   = [];
	this.messages_cache = [];
	this.tags_cache     = [];
	this.contacts_cache = [];
	this.keybindings    = [
  	["normal", "/",      function() { $("#search-query").focus(); return false; }],
  	["normal", "c",      function() { mailpile.compose(); }],
  	["normal", "g i",    function() { mailpile.go("/in/inbox/"); }],
  	["normal", "g d",    function() { mailpile.go("/in/drafts/"); }],
  	["normal", "g c",    function() { mailpile.go("/contact/list/"); }],
  	["normal", "g n c",  function() { mailpile.go("/contact/add/"); }],
  	["normal", "g t",    function() { mailpile.go("/tag/list/"); }],
  	["normal", "g n t",  function() { mailpile.go("/tag/add/"); }],
  	["normal", "g s",    function() { mailpile.go("/settings/profiles/"); }],
  	["normal", "command+z",  function() { alert('Undo Something ') }],
  	["normal", ["a"], function() { mailpile.keybinding_move_message(''); }],
  	["normal", ["d"], function() { mailpile.keybinding_move_message('trash'); }],
  	["normal", ["r"], function() { mailpile.bulk_action_read(); }],
  	["normal", ["s"], function() { mailpile.keybinding_move_message('spam'); }],
  	["normal", ["t"], function() { mailpile.render_modal_tags(); }],
  	["normal", ["u"], function() { mailpile.bulk_action_unread(); }],
    ["global", "esc", function() {
  		$('input[type=text]').blur();
  		$('textarea').blur();
    }]
  ];
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
  	tag_list     : "/api/0/tag/list/",
  	tag_add      : "/api/0/tag/add/",
  	tag_update   : "/api/0/settings/set/",
  	search_new   : "/api/0/search/?q=in%3Anew",
    search       : "/api/0/search/",
  	settings_add : "/api/0/settings/add/"
  	
	}
	this.urls = {
  	message_draft : "/message/draft/=",
  	message_sent  : "/thread/="
	}
	this.plugins = [];
	this.autosave = {};
};

MailPile.prototype.go = function(url) {
  window.location.href = url;
};

MailPile.prototype.bulk_cache_add = function(type, value) {
  if (_.indexOf(this[type], value) < 0) {
    this[type].push(value);
  }
};

MailPile.prototype.bulk_cache_remove = function(type, value) {
  if (_.indexOf(this[type], value) > -1) {
    this[type] = _.without(this[type], value);
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
    var new_content_width = $(window).width() - sidebar_width;
  
    $('#content-tools').css('position', 'fixed')
    $('.sub-navigation').width(content_width);
    $('#thread-title').width(content_width);
  
    console.log(fix_content_view_height);
    console.log(content_tools_height);
  
    // Set Content View
    $('#content-tools, .sub-navigation, .bulk-actions').width(new_content_width);
    $('#content-view').css({'height': fix_content_view_height, 'top': content_tools_height});
  };

  dynamic_sizing();

  // Resize Elements on Drag
  window.onresize = function(event) {
    dynamic_sizing();
  };

  // Show Mailboxes
  if ($('#sidebar-tag-outbox').find('span.sidebar-notification').html() !== undefined) {
    $('#sidebar-tag-outbox').show();
  }

  // Mousetrap Keybindings
	for (item in mailpile.keybindings) {
	  var keybinding = mailpile.keybindings[item];
		if (keybinding[0] == "global") {
			Mousetrap.bindGlobal(keybinding[1], keybinding[2]);
		} else {
      Mousetrap.bind(keybinding[1], keybinding[2]);
		}
	}

};

MailPile.prototype.command = function(command, data, method, callback) {
  if (method != "GET" && method != "POST") {
    method = "GET";
  }
  $.ajax({
    url      : command,
    type     : method,
    dataType : 'json',
    success  : callback,
  });
}

var mailpile = new MailPile();
var favicon = new Favico({animation:'popFade'});

// Non-exposed functions: www, setup
$(document).ready(function() {

  // Render
  mailpile.render();

});


