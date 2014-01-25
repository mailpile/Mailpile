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
}


MailPile.prototype.bulk_cache_add = function(mid) {
  if (_.indexOf(this.bulk_cache, mid) < 0) {
    this.bulk_cache.push(mid);
  }
};


MailPile.prototype.bulk_cache_remove = function(mid) {
  if (_.indexOf(this.bulk_cache, mid) > -1) {
    this.bulk_cache = _.without(this.bulk_cache, mid);
  }
}


MailPile.prototype.keybindings_loadfromserver = function() {
	var that = this;
	this.json_get("help", {}, function(data) {
		console.log(data);
		for (key in data[0].result.commands) {
			console.log(key);
		}
	});
}


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

  // Update New Count (other stuff in the future)
  var getNewMessages = function() {    
    $.ajax({
		  url			 : mailpile.api.search_new,
		  type		 : 'GET',
		  dataType : 'json',
	    success  : function(response) {
        if (response.status == 'success') {
          console.log('new message count: ' + response.result.total);
          favicon.badge(response.result.total);
        }
	    }
	  }); 
  }


  // Update Counts  
  setInterval(function() {
    getNewMessages();
  }, 300000);


  /* Set View Size */
  if (!localStorage.getItem('view_size')) {
    localStorage.setItem('view_size', mailpile.defaults.view_size);
  }

  $('#header').addClass(localStorage.getItem('view_size'));
  $('#container').addClass(localStorage.getItem('view_size'));
  $('#sidebar').addClass(localStorage.getItem('view_size'));
  $('#pile-results').addClass(localStorage.getItem('view_size'));

  $.each($('a.change-view-size'), function() {
    if ($(this).data('view_size') == localStorage.getItem('view_size')) {
      $(this).addClass('view-size-selected');
    }
  });


  // Dynamic CSS Reiszing
  var content_width  = $(window).width() - $('#sidebar').width();
  var content_height = $(window).height() - $('#topbar').height();
  var sidebar_height = $('#sidebar').height();
  var content_tools_height = $('#content-tools').height();
  var fix_content_view_height = sidebar_height - content_tools_height;

  $('.sub-navigation').width(content_width);
  $('#thread-title').width(content_width);

  // Set Content View
  $('#content-view').css('height', fix_content_view_height).css('top', content_tools_height);
  
  

  // Resize Elements on Drag
  window.onresize = function(event) {
    var new_content_width = $(window).width() - $('#sidebar').width();
    $('.sub-navigation, .bulk-actions').width(new_content_width);
    
  }



  if ($('#sidebar-tag-outbox').find('span.sidebar-notification').html() === undefined) {
    $('#sidebar-tag-outbox').hide();
  }

});



/* Pile - Change Size */
$(document).on('click', 'a.change-view-size', function(e) {

  e.preventDefault();

  var current_size = localStorage.getItem('view_size');
  var new_size = $(this).data('view_size');

  // Update Link Selected
  $('a.change-view-size').removeClass('view-size-selected');
  $(this).addClass('view-size-selected');

  // Update View Sizes
  $('#header').removeClass(current_size).addClass(new_size);
  $('#container').removeClass(current_size).addClass(new_size);
  $('#sidebar').removeClass(current_size).addClass(new_size);
  $('#pile-results').removeClass(current_size).addClass(new_size);

  // Data
  localStorage.setItem('view_size', new_size);

});
  



