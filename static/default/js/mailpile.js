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
	this.search_cache   = [];
	this.bulk_cache     = [];
	this.keybindings    = [];
	this.commands       = [];
	this.graphselected  = [];
	this.defaults       = {
  	view_size: "comfy"
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


MailPile.prototype.results_graph = function() {

  // Change Navigation 
	$('#btn-display-graph').addClass('navigation-on');
	$('#btn-display-list').removeClass('navigation-on');

	// Show & Hide Pile View
	$('#pile-results').hide('fast', function() {

	  $('#form-pile-results').hide('fast');
    $('.pile-speed').hide('fast');
    $('#footer').hide('fast');
    $('#sidebar').hide('fast');

	  $('#pile-graph').hide().delay(1000).show();
	});

  // Determine & Set Height
  var available_height = $(window).height() - ($('#header').height() + $('.sub-navigation').height());

  $('#pile-graph-canvas').height(available_height);
  $("#pile-graph-canvas-svg").attr('height', available_height).height(available_height);

	args = $('#pile-graph-canvas-svg').data("searchterms");

	d3.json("/api/0/shownetwork/?q=" + args, function(graph) {
		graph = graph.result;
		console.log(graph);
    
    console.log(available_height);
    				
		var width = 640; // $("#pile-graph-canvas").width();
		var height = available_height;
		var force = d3.layout.force()
	   				.charge(-300)
	   				.linkDistance(75)
	   				.size([width, height]);

		var svg = d3.select("#pile-graph-canvas-svg");
		$("#pile-graph-canvas-svg").empty();

		var color = d3.scale.category20();

		var tooltip = d3.select("body")
		    .append("div")
	    	.style("position", "absolute")
	    	.style("z-index", "10")
	    	.style("visibility", "hidden")
	    	.text("a simple tooltip");

		force
			.nodes(graph.nodes)
	    	.links(graph.links)
	    	.start();

		var link = svg.selectAll(".link")
			.data(graph.links)
			.enter().append("line")
			.attr("class", "link")
			.style("stroke-width", function(d) { return Math.sqrt(3*d.value); });

		var node = svg.selectAll(".node")
		      .data(graph.nodes)
			  .enter().append("g")
		      .attr("class", "node")
		      .call(force.drag);

		node.append("circle")
			.attr("r", 8)
		    .style("fill", function(d) { return color("#3a6b8c"); })

	    node.append("text")
	    	.attr("x", 12)
	    	.attr("dy", "0.35em")
	    	.style("opacity", "0.3")
	    	.text(function(d) { return d.email; });

	    link.append("text").attr("x", 12).attr("dy", ".35em").text(function(d) { return d.type; })

	   	node.on("click", function(d, m, q) {
	   		// d.attr("toggled", !d.attr("toggled"));
	   		// d.style("color", "#f00");
	   		if (mailpile.graphselected.indexOf(d["email"]) < 0) {
		   		d3.select(node[q][m]).selectAll("circle").style("fill", "#4b7945");
		   		mailpile.graphselected.push(d["email"]);
	   		} else {
	   			mailpile.graphselected.pop(d["email"]);
	   			d3.select(node[q][m]).selectAll("circle").style("fill", "#3a6b8c");
	   		}
	   		mailpile.graph_actionbuttons();
	   	});
		node.on("mouseover", function(d, m, q) {
			d3.select(node[q][m]).selectAll("text").style("opacity", "1");
		});
		node.on("mouseout", function(d, m, q) {
			d3.select(node[q][m]).selectAll("text").style("opacity", "0.3");
		});

		force.on("tick", function() {
			link.attr("x1", function(d) { return d.source.x; })
			    .attr("y1", function(d) { return d.source.y; })
			    .attr("x2", function(d) { return d.target.x; })
			    .attr("y2", function(d) { return d.target.y; });

			node.attr("transform", function(d) { return "translate(" + d.x + "," + d.y + ")"; });
		});
	});

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


var mailpile = new MailPile();



// Non-exposed functions: www, setup
$(document).ready(function() {


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
  



