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
		url = "/api/0/" + cmd + ".json";
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
	$('#btn-display-list').addClass('navigation-on');
	$('#btn-display-graph').removeClass('navigation-on');
	$('#pile-graph').hide();
	$('#pile-results').show();
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
	$('#btn-display-graph').addClass('navigation-on');
	$('#btn-display-list').removeClass('navigation-on');
	$('#pile-results').hide();
	$('#pile-graph').show();
	args = $('#pile-graph-canvas-svg').data("searchterms");

	d3.json("/api/0/shownetwork/?q=" + args, function(graph) {
		graph = graph.result;
		// console.log(graph);
		var width = 640; // $("#pile-graph-canvas").width();
		var height = 640; // $("#pile-graph-canvas").height();
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

    $('#sidebar').addClass(localStorage.getItem('view_size'));
    $('#sub-navigation').addClass(localStorage.getItem('view_size'));
    $('#bulk-actions').addClass(localStorage.getItem('view_size'));
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
  $('#sidebar').removeClass(current_size).addClass(new_size);
  $('#sub-navigation').removeClass(current_size).addClass(new_size);
  $('#bulk-actions').removeClass(current_size).addClass(new_size);
  $('#pile-results').removeClass(current_size).addClass(new_size);

  // Data
  localStorage.setItem('view_size', new_size);

});
  





/* **********************************************
     Begin messages.js
********************************************** */

/* Status Messages */


var statusHeaderPadding = function() {

	if ($('#header').css('position') === 'fixed') {
		var padding = $('#header').height() + 50;
	}
	else {
		var padding = 0;
	}

	return padding;
};



var statusMessage = function(status, message_text, complete, complete_action) {

  var default_messages = {
    "success" : "Success, we did exactly what you asked.",
    "info"    : "Here is a basic info update",
    "debug"   : "What kind of bug is this bug, it's a debug",
    "warning" : "This here be a warnin to you, just a warnin mind you",
    "error"   : "Whoa cowboy, you've mozyed on over to an error"
  }

  var message = $('#messages').find('div.' + status);

  if (message_text == undefined) {
    message_text = default_messages[status];
  }

  // Show Message
  message.find('span.message-text').html(message_text),
  message.fadeIn(function() {

    // Set Padding Top for #content
	  $('#header').css('padding-top', statusHeaderPadding());
  });

	// Complete Action
	if (complete == undefined) {

  }
	else if (complete == 'hide') {
		message.delay(5000).fadeOut('normal', function()
		{
			message.find('span.message-text').empty();
		});
	}
	else if (options.complete == 'redirect') {
		setTimeout(function() { window.location.href = complete_action }, 5000);
	}

  return false;
}


$(document).ready(function() {


  /* Message Close */
	$('.message-close').on('click', function() {
		$(this).parent().fadeOut(function() {
			$('#header').css('padding-top', statusHeaderPadding());
		});
	});

});

/* **********************************************
     Begin compose.js
********************************************** */

/* Compose */


  /* Create New Blank Message */
  $(document).on('click', '#button-compose', function() {
		$.ajax({
			url			 : '/api/0/message/compose/',
			type		 : 'POST',
			data     : {},
			dataType : 'json'  
    }).done(function(response) {
        if (response.status == 'success') {
          window.location.href = '/message/draft/=' + response.result.created + '/';
        }
        else {
          statusMessage(response.status, response.message);
        }      
    });
  });



  /* Adding Recipients */
  if ($('#form-compose').length) {

    $.getJSON('http://localhost:33411/static/contacts.json', function(contacts) {
        
      var formatContactResult = function(state) {
        if (!state.id) return state.text;
        return "<span class='icon-user'></span> &nbsp;" + state.text;
      }          
        
      $("#compose-to, #compose-cc, #compose-bcc").select2({
        tags: contacts[0].result.contacts,          // Load contact list (items in javascrupt array [])
        multiple: true,
        allowClear: true,
        placeholder: 'type name or email address',  // Placeholder
        width: '94%',                               // Width of input element
        maximumSelectionSize: 50,                   // Limits number of items added
        tokenSeparators: [",", " - "],
        formatResult: formatContactResult,
        formatSelection: formatContactResult,    
        formatSelectionTooBig: function() {
          return 'You\'ve added the maximum contacts allowed, to increase this go to <a href="#">settings</a>';
        }
      });

      $("#compose-to, #compose-cc, #compose-bcc").on("change", function() {
        $("#compose-to_val").html($("#compose-to").val());
      });

      $("#compose-to, #compose-cc, #compose-bcc").select2("container").find("ul.select2-choices").sortable({
        containment: 'parent',
        start: function() { 
          $("#compose-to, #compose-cc, #compose-bcc").select2("onSortStart");
        },
        update: function() {
          $("#compose-to, #compose-cc, #compose-bcc").select2("onSortEnd");
        }
      });
    });
  }



  /* Send & Save */
  $(document).on('click', '.compose-action', function(e) {
  
    e.preventDefault();
    var action = $(this).val();
  
    if (action == 'send') {
  	  var action_url     = 'update/send/';
  	  var action_status  = 'success';
  	  var action_message = 'Your message was sent <a id="status-undo-link" data-action="undo-send" href="#">undo</a>';
    }
    else if (action == 'save') {
  	  var action_url     = 'update/';
  	  var action_status  =  'info';
  	  var action_message = 'Your message was saved';
    }
  
  	$.ajax({
  		url			 : '/api/0/message/' + action_url,
  		type		 : 'POST',
  		data     : $('#form-compose').serialize(),
  		dataType : 'json',
  	  success  : function(response) {
  
        if (action == 'send' && response.status == 'success') {
          window.location.href = '/in/Sent/?ui_sent=' + response.result.messages[0].mid
        }
        else {
          statusMessage(response.status, response.message);
        }
  	  }
  	});
  });


/* **********************************************
     Begin pile.js
********************************************** */

/* Pile */


  


  /* Filter New */
  $(document).on('click', '.button-sub-navigation', function() {

    var filter = $(this).data('filter');
    $('#sub-navigation ul.left li').removeClass('navigation-on');

    if (filter == 'in_new') {

      $('#display-new').addClass('navigation-on');
      $('tr').hide('fast', function() {
        $('tr.in_new').show('fast');
      });
    }
    else if (filter == 'in_later') {

      $('#display-later').addClass('navigation-on');
      $('tr').hide('fast', function() {
        $('tr.in_later').show('fast');
      });
    }
    else {

      $('#display-all').addClass('navigation-on');
      $('tr.result').show('fast');
    }

    return false;
  });




	/* Bulk Actions */
	$(document).on('click', '.bulk-action', function(e) {

		e.preventDefault();
		var checkboxes = $('#pile-results input[type=checkbox]');
		var action = $(this).attr('href');
		var count = 0;

		$.each(checkboxes, function() {
			if ($(this).val() === 'selected') {
				console.log('This is here ' + $(this).attr('name'));
				count++;
			}
		});

		alert(count + ' items selected to "' + action.replace('#', '') + '"');
	});


	/* Result Actions */
	var pileActionSelect = function(item) {

    // Data Stuffs    
    mailpile.bulk_cache_add(item.data('mid'));

		// Increment Selected
		$('#bulk-actions-selected-count').html(parseInt($('#bulk-actions-selected-count').html()) + 1);

		// Show Actions
		$('#bulk-actions').slideDown('slow');

		// Style & Select Checkbox
		item.removeClass('result').addClass('result-on')
		.data('state', 'selected')
		.find('td.checkbox input[type=checkbox]')
		.val('selected')
		.prop('checked', true);
	}


	var pileActionUnselect = function(item) {

    // Data Stuffs    
    mailpile.bulk_cache_remove(item.data('mid'));

		// Decrement Selected
		var selected_count = parseInt($('#bulk-actions-selected-count').html()) - 1;

		$('#bulk-actions-selected-count').html(selected_count);

		// Hide Actions
		if (selected_count < 1) {
			$('#bulk-actions').slideUp('slow');
		}

		// Style & Unselect Checkbox
		item.removeClass('result-on').addClass('result')
		.data('state', 'normal')
		.find('td.checkbox input[type=checkbox]')
		.val('normal')
		.prop('checked', false);
	}


	$(document).on('click', '#pile-results tr', function(e) {
		if (e.target.href === undefined && $(this).data('state') === 'selected') {
			pileActionUnselect($(this));
		}
		else if (e.target.href === undefined) {
			pileActionSelect($(this));
		}
	});



  /* Dragging */
  $('td.draggable').draggable({
    containment: "#container",
    scroll: false,
    revert: true,
    helper: function(event) {

      var selected_count = parseInt($('#bulk-actions-selected-count').html());
      
      if (selected_count == 0) {
        drag_count = '1 message</div>';
      }
      else {
        drag_count = selected_count + ' messages';
      }

      return $('<div class="pile-results-drag ui-widget-header"><span class="icon-message"></span> Move ' + drag_count + '</div>');
    },
    stop: function(event, ui) {
      console.log('done dragging things');
    }
  });



  /* Dropping */
  $('li.sidebar-tags-draggable').droppable({
    accept: 'td.draggable',
    activeClass: 'sidebar-tags-draggable-hover',
    hoverClass: 'sidebar-tags-draggable-active',
    tolerance: 'pointer',
    drop: function(event, ui) {

      var getDelTag = function() {
        if ($.url.segment(0) === 'in') {
          return $.url.segment(1);
        }
        return '';
      }
      
      // Add MID to Cache    
      mailpile.bulk_cache_add(ui.draggable.parent().data('mid'));
    
      // Fire at Willhelm
  	  $.ajax({
  		  url			 : '/api/0/tag/',
  		  type		 : 'POST',
  		  data     : {
          add: $(this).data('tag_name'),
          del: getDelTag,
          mid: mailpile.bulk_cache
        },
  		  dataType : 'json',
  	    success  : function(response) {
          
          if (response.status == 'success') {
            $.each(mailpile.bulk_cache, function(key, mid) {
              $('#pile-message-' + mid).fadeOut('fast');
            });  
          } else {
            statusMessage(response.status, response.message);
          }
  	    }
  	  });  	  
    }
  });

/* **********************************************
     Begin tags.js
********************************************** */

/* Tags */


  /* Show Tag Add Form */
  $(document).on('click', '#button-tag-add', function(e) {
  	
  	e.preventDefault();
  
  	$('#tags-list').hide();
    $('#tag-add').show();
  	
  	$this_nav = $(this);
    console.log($this_nav);
  
    $('#sub-navigation ul li').removeClass('navigation-on');
    $(this).parent().addClass('navigation-on');
  
  });
  

  /* API - tag/add */  
  $(document).on('submit', '#form-tag-add', function(e) {
  
    e.preventDefault();
    var tag_data = $('#form-tag-add').serialize();
    console.log($(this));
  
  	$.ajax({
  		url			 : $(this).attr('action'),
  		type		 : 'POST',
  		data     : tag_data,
  		dataType : 'json',
  	  success  : function(response) {
  
        statusMessage(response.status, response.message);
  
        if (response.status == 'success') {
          console.log(response);
          //window.location.href = ''
        }
  	  }
  	});
    
  });


/* **********************************************
     Begin search.js
********************************************** */

/* Search */


$(document).ready(function() {


	/* Hide Various Things */
	$('#search-params, #bulk-actions').hide();

	/* Search Box */
	$('#qbox').bind("focus", function(key) {
		$('#search-params').slideDown('fast');
	});

	$('#qbox').bind("blur", function(key) {
		$('#search-params').slideUp('fast');
	});

	for (item in keybindings) {
		if (item[1] == "global") {
			Mousetrap.bindGlobal(item[0], item[2]);
		} else {
			Mousetrap.bind(item[0], item[2]);
		}
	}

	
});
