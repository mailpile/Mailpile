// If no console.log() exists
if (!window.console) window.console = { log: $.noop, group: $.noop, groupEnd: $.noop, info: $.noop, error: $.noop };


Number.prototype.pad = function(size){
	// Unfortunate padding function....
	if(typeof(size) !== "number"){size = 2;}
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
  	tag          : "/api/0/tag/",
  	tag_add      : "/api/0/tag/add/",
  	search_new   : "/api/0/search/?q=in%3Anew",
  	settings_add : "/api/0/settings/add/"
	}
	this.urls = {
  	message_draft : "/message/draft/=",
  	message_sent  : "/in/Sent/?ui_sent="
	}
	this.plugins = [];
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

MailPile.prototype.add = function() {}
MailPile.prototype.attach = function() {}
MailPile.prototype.compose = function() {}
MailPile.prototype.delete = function() {}
MailPile.prototype.extract = function() {}
MailPile.prototype.filter = function() {}
MailPile.prototype.help = function() {}
MailPile.prototype.load = function() {}
MailPile.prototype.mail = function() {}
MailPile.prototype.forward = function() {}
MailPile.prototype.next = function() {}
MailPile.prototype.order = function() {}
MailPile.prototype.optimize = function() {}
MailPile.prototype.previous = function() {}
MailPile.prototype.print = function() {}
MailPile.prototype.reply = function() {}
MailPile.prototype.rescan = function() {}


MailPile.prototype.compose = function() {

  var form = $('<form action="' + url + '" method="post">' +
    '<input type="text" name="api_url" value="' + Return_URL + '" />' +
    '</form>');
  $('body').append(form);
  $(form).submit();
  console.log('yo here we go');

  // Set Everything to Empty
  $('#compose-to, #compose-cc, #compose-bcc').select2('val', '');
  $('#compose-subject').val('');
  $('#compose-body').val('');
  $('#compose-attachments-list').html('');

}

MailPile.prototype.gpgrecvkey = function(keyid) {
	console.log("Fetching GPG key 0x" + keyid);
	mailpile.json_get("gpg recv_key", {}, function(data) {
		console.log("Fetch command execed for GPG key 0x" + keyid + ", resulting in:");
		console.log(data);
	});
}

MailPile.prototype.gpglistkeys = function() {
	mailpile.json_get("gpg list", {}, function(data) {
		$("#content").append('<div class="dialog" id="gpgkeylist"></div>');
		for (k in data.results) {
			key = data.results[k]
			$("#gpgkeylist").append("<li>Key: " + key.uids[0].replace("<", "&lt;").replace(">", "&gt;") + ": " + key.pub.keyid + "</li>");
		}
	});
}

MailPile.prototype.search = function(q) {
	var that = this;
	$("#qbox").val(q);
	this.json_get("search", {"q": q}, function(data) {
		if ($("#results").length == 0) {
			$("#content").prepend('<table id="results" class="results"><tbody></tbody></table>');
		}
		$("#results tbody").empty();
		for (var i = 0; i < data.results.length; i++) {
			msg_info = data.results[i];
			msg_tags = data.results[i].tags;
			d = new Date(msg_info.date*1000)
			zpymd = d.getFullYear() + "-" + (d.getMonth()+1).pad(2) + "-" + d.getDate().pad(2);
			ymd = d.getFullYear() + "-" + (d.getMonth()+1) + "-" + d.getDate();
			taghrefs = msg_tags.map(function(e){ return '<a onclick="mailpile.search(\'\\' + e + '\')">' + e + '</a>'}).join(" ");
			tr = $('<tr class="result"></tr>');
			tr.addClass((i%2==0)?"even":"odd");
			tr.append('<td class="checkbox"><input type="checkbox" name="msg_' + msg_info.id + '"/></td>');
			tr.append('<td class="from"><a href="' + msg_info.url + '">' + msg_info.from + '</a></td>');
			tr.append('<td class="subject"><a href="' + msg_info.url + '">' + msg_info.subject + '</a></td>');
			tr.append('<td class="tags">' + taghrefs + '</td>');
			tr.append('<td class="date"><a onclick="mailpile.search(\'date:' + ymd + '\');">' + zpymd + '</a></td>');
			$("#results tbody").append(tr);
		}
		that.loglines(data.chatter);
	});
}

MailPile.prototype.go = function(q) {
	console.log("Going to ", q);
	window.location.href = q;
}

MailPile.prototype.set = function(key, value) {
	var that = this;
	this.json_get("set", {"args": key + "=" + value}, function(data) {
		if (data.status == "ok") {
			that.notice("Success: " + data.loglines[0]);
		} else if (data.status == "error") {
			this.error(data.loglines[0]);
		}
	});
}

MailPile.prototype.tag = function(msgids, tags) {}
MailPile.prototype.addtag = function(tagname) {}
MailPile.prototype.unset = function() {}
MailPile.prototype.update = function() {}

MailPile.prototype.view = function(idx, msgid) {
	var that = this;
	this.json_get("view", {"idx": idx, "msgid": msgid}, function(data) {
		if ($("#results").length == 0) {
			$("#content").prepend('<table id="results" class="results"><tbody></tbody></table>');
		}
		$("#results").empty();
		$that.loglines(data.chatter);
	})
}

MailPile.prototype.json_get = function(cmd, params, callback) {
	var url;
	if (cmd == "view") {
		url = "/=" + params["idx"] + "/" + params["msgid"] + ".json";
	} else {
		url = "/api/0/" + cmd;
	}
	$.getJSON(url, params, callback);
}

MailPile.prototype.loglines = function(text) {
	$("#loglines").empty();
	for (var i = 0; i < text.length; i++) {
		$("#loglines").append(text[i] + "\n");
	}
}

MailPile.prototype.notice = function(msg) {
	console.log("NOTICE: " + msg);
}

MailPile.prototype.error = function(msg) {
	console.log("ERROR: " + msg);
}

MailPile.prototype.warning = function(msg) {
	console.log("WARNING: " + msg);
}


MailPile.prototype.results_list = function() {

  // Navigation
	$('#btn-display-list').addClass('navigation-on');
	$('#btn-display-graph').removeClass('navigation-on');
	
	// Show & Hide View
	$('#pile-graph').hide('fast', function() {

    $('#sidebar').show('normal');
    $('#form-pile-results').show('normal');
    $('#pile-results').show('fast');
    $('.pile-speed').show('normal');
    $('#footer').show('normal');
    $('#sidebar').show('normal');

	});

}

MailPile.prototype.graph_actionbuttons = function() {
	if (this.graphselected.length >= 1) {
		$("#btn-compose-message").show();
	} else {
		$("#btn-compose-message").hide();
	}
	if (this.graphselected.length >= 2) {
		$("#btn-found-group").show();
	} else {
		$("#btn-found-group").hide();
	}
}

MailPile.prototype.focus_search = function() {
	$("#qbox").focus(); return false;
}



var keybindings = [
	["/", 		"normal",	function() { $("#qbox").focus(); return false; }],
	["C", 		"normal",	function() { mailpile.go("/_/compose/"); }],
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


var favicon = new Favico({
    animation:'popFade'
});


var mailpile = new MailPile();



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
  if (localStorage.getItem('view_size')) {

    $('#header').addClass(localStorage.getItem('view_size'));
    $('#container').addClass(localStorage.getItem('view_size'));
    $('#sidebar').addClass(localStorage.getItem('view_size'));
    $('#pile-results').addClass(localStorage.getItem('view_size'));

    $.each($('a.change-view-size'), function() {
      if ($(this).data('view_size') == localStorage.getItem('view_size')) {
        $(this).addClass('view-size-selected');
      }
    });
  }
  else {
    localStorage.setItem('view_size', mailpile.defaults.view_size);
  }


  
  // Load Scrollers
  /*
  $(".nano").nanoScroller({ 
    alwaysVisible: true,
    sliderMinHeight: 40
  });
  */


  $('.topbar-nav a').qtip({
    style: {
     tip: {
        corner: 'top center',
        mimic: 'top center',
        border: 0,
        width: 10,
        height: 10
      },
      classes: 'qtip-tipped'
    },
    position: {
      my: 'top center',
      at: 'bottom center',
			viewport: $(window),
			adjust: {
				x: 0,  y: 5
			}
    },
    show: {
      delay: 350
    }
  });


  $('a.bulk-action').qtip({
    style: {
      classes: 'qtip-tipped'
    },
    position: {
      my: 'top center',
      at: 'bottom center',
			viewport: $(window),
			adjust: {
				x: 0,  y: 5
			}
    }
  });


  $('.message-privacy-state').qtip({
    style: {
     tip: {
        corner: 'right center',
        mimic: 'right center',
        border: 0,
        width: 10,
        height: 10
      },
      classes: 'qtip-tipped'
    },
    position: {
      my: 'right center',
      at: 'left center',
			viewport: $(window),
			adjust: {
				x: -5,  y: 0
			}
    },
    show: {
      delay: 50
    }
  });


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
  



