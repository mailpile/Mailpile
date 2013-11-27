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
  



/* Profile Add */
$(document).on('submit', '#form-profile-add', function(e) {

  e.preventDefault();

  var profile_data = {
    name : $('#profile-add-name').val(),
    email: $('#profile-add-email').val()
  };

  var smtp_route = $('#profile-add-username').val() + ':' + $('#profile-add-password').val() + '@' + $('#profile-add-server').val() + ':' + $('#profile-add-port').val();

  if (smtp_route !== ':@:25') {
    profile_data.route = 'smtp://' + smtp_route;
  }

	$.ajax({
    url      : mailpile.api.settings_add,
		type     : 'POST',
		data     : {profiles: JSON.stringify(profile_data)},
		dataType : 'json',
    success  : function(response) {

      statusMessage(response.status, response.message);
      if (response.status === 'success') {
        console.log(response);
      }
    }
	});

});MailPile.prototype.search = function(q) {
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


MailPile.prototype.focus_search = function() {
	$("#qbox").focus(); return false;
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


$(document).ready(function() {

	/* Hide Various Things */
	$('#search-params, #bulk-actions').hide();

	/* Search Box */
	$('#button-search-options').on("click", function(key) {
		$('#search-params').slideDown('fast');
	});

	$('#button-search-options').on("blur", function(key) {
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


var contactActionSelect = function(item) {

  console.log('select things');

  // Data Stuffs    
  mailpile.bulk_cache_add();

	// Increment Selected
	$('#bulk-actions-selected-count').html(parseInt($('#bulk-actions-selected-count').html()) + 1);

	// Show Actions
	$('#bulk-actions').slideDown('slow');

	// Style & Select Checkbox
	item.removeClass('result').addClass('result-on').data('state', 'selected');
};


var contactActionUnselect = function(item) {

  console.log('unselect things');

  // Data Stuffs    
  mailpile.bulk_cache_remove();

	// Decrement Selected
	var selected_count = parseInt($('#bulk-actions-selected-count').html()) - 1;

	$('#bulk-actions-selected-count').html(selected_count);

	// Hide Actions
	if (selected_count < 1) {
		$('#bulk-actions').slideUp('slow');
	}

	// Style & Unselect Checkbox
	item.removeClass('result-on').addClass('result').data('state', 'normal');
};



$(document).on('click', '#contacts-list div.boxy', function(e) {
	if (e.target.href === undefined && $(this).data('state') === 'selected') {
		contactActionUnselect($(this));
	}
	else if (e.target.href === undefined) {
		contactActionSelect($(this));
	}
});


$(document).on('click', '.compose-to-email', function(e) {
  e.preventDefault();
  mailpile.compose({
    to: $(this).data('email')
  });
});var statusHeaderPadding = function() {

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
	  // $('#header').css('padding-top', statusHeaderPadding());
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
			//$('#header').css('padding-top', statusHeaderPadding());
		});
	});

});MailPile.prototype.tag = function(msgids, tags) {}
MailPile.prototype.addtag = function(tagname) {}


/* Show Tag Add Form */
$(document).on('click', '#button-tag-add', function(e) {
	
  e.preventDefault();

  $('#tags-list').hide();
  $('#tag-add').show();

  $('#sub-navigation ul li').removeClass('navigation-on');
  $(this).parent().addClass('navigation-on');
});


/* API - Tag Add */
$(document).on('submit', '#form-tag-add', function(e) {

  e.preventDefault();
  var tag_data = $('#form-tag-add').serialize();

  $.ajax({
    url: mailpile.api.tag_add,
    type: 'POST',
    data: tag_data,
    dataType : 'json',
    success: function(response) {

      statusMessage(response.status, response.message);

      if (response.status === 'success') {
        console.log(response);
      }
    }
  });
});MailPile.prototype.gpgrecvkey = function(keyid) {
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
}/* Filter New */
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


$(document).on('click', '#pile-results tr.result', function(e) {
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
		  url			 : mailpile.api.tag,
		  type		 : 'POST',
		  data     : {
        add: $(this).data('tag_name'),
        del: getDelTag,
        mid: mailpile.bulk_cache
      },
		  dataType : 'json',
	    success  : function(response) {

        if (response.status == 'success') {

          // Update Pile View
          $.each(mailpile.bulk_cache, function(key, mid) {
            $('#pile-message-' + mid).fadeOut('fast');
          });
          
          // Empty Bulk Cache
          mailpile.bulk_cache = [];
          
        } else {
          statusMessage(response.status, response.message);
        }
	    }
	  });  	  
  }
});// Non-exposed functions: www, setup
$(document).ready(function() {

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
    },
    events: {
      show: function(event, api) {

        $('.compose-to').css('background-color', '#fbb03b');
        $('.compose-cc').css('background-color', '#fbb03b');           
        $('.compose-bcc').css('background-color', '#fbb03b');
        $('.compose-from').css('background-color', '#fbb03b');
        $('.compose-subject').css('background-color', '#fbb03b');

        $('.compose-message').css('background-color', '#a2d699');
        $('.compose-attachments').css('background-color', '#a2d699');

        console.log('Checking this out'); 
      },
      hide: function(event, api) {

        $('.compose-to').css('background-color', '#ffffff');
        $('.compose-cc').css('background-color', '#ffffff');           
        $('.compose-bcc').css('background-color', '#ffffff');
        $('.compose-from').css('background-color', '#ffffff');
        $('.compose-subject').css('background-color', '#ffffff');

        $('.compose-message').css('background-color', '#ffffff');
        $('.compose-attachments').css('background-color', '#ffffff');
        
      }
    }
  });


  $('.compose-to-email').qtip({
    content: {
      text: 'Email This Address'
    },
    style: {
      classes: 'qtip-tipped'
    },
    position: {
      my: 'bottom center',
      at: 'top center',
			viewport: $(window),
			adjust: {
				x: 0,  y: 0
			}
    },
    show: {
      delay: 500
    }
  });
  

});/* Generate New Draft MID */
MailPile.prototype.compose = function(data) {

  $.ajax({
    url      : mailpile.api.compose,
    type     : 'POST',
    data     : data,
    dataType : 'json'
  })
  .done(function(response) {

    if (response.status == 'success') {
      window.location.href = mailpile.urls.message_draft + response.result.created + '/';
    } else {
      statusMessage(response.status, response.message);
    }
  });
}


/* Add Attachment */
MailPile.prototype.attach = function() {}


/* Create New Blank Message */
$(document).on('click', '#button-compose', function(e) {
	e.preventDefault();
	mailpile.compose();
});


/* Is Compose Page -  Probably want to abstract this differently */
if ($('#form-compose').length) {

  // Reset tabindex for To: field
  $('#qbox').attr('tabindex', '');


  var composeContactSelected = function(contact) {
    if (contact.object.secure) {
      console.log('Whee keys ' + contact.object.keys[0].fingerprint);
      $('.message-privacy-state').attr('title', 'The message is encrypted. The recipients & subject are not');
      $('.message-privacy-state').removeClass('icon-unencrypted').addClass('icon-encrypted');
      $('.message-privacy-state').parent().addClass('bounce');
    } else {
    }
  }

  var formatComposeId = function(object) {
    if (object.fn != "" && object.address != object.fn) {
      return object.fn + ' <' + object.address + '>';
    } else {
      return object.address;
    }
  }

  var formatComposeResult = function(state) {
    var avatar = '<span class="icon-user"></span>';
    var secure = '';
    if (state.photo) {
      avatar = '<img src="' + state.photo + '">';
    }    
    if (state.secure) {
      secure = '<span class="icon-verified"></span>';
    }
    return '<span class="compose-select-avatar">' + avatar + '</span><span class="compose-select-name">' + state.fn + secure + '<br><span class="compose-select-address">' + state.address + '</span></span>';
  }

  var formatComposeSelection = function(state) {
    var avatar = '<span class="icon-user"></span>';
    var secure = '';
    if (state.photo) {
      avatar = '<span class="avatar"><img src="' + state.photo + '"></span>';
    }
    if (state.secure) {
      secure = '<span class="icon-verified"></span>';
    }
    return avatar + '<span class="compose-choice-name" title="' + state.address + '">' + state.fn + secure + '</span>';
  }

  var closeMenu = function() {
    console.log($('#compose-to').val());
    $('#compose-to').select2("close");
  }

  $('#compose-to, #compose-cc, #compose-bcc').select2({
    id: formatComposeId,
    ajax: { // instead of writing the function to execute the request we use Select2's convenient helper
      url: mailpile.api.contacts,
      quietMillis: 1,
      cache: true,
      dataType: 'json',
      data: function(term, page) {
        return {
          q: term
        };
      },
      results: function(response, page) {
        // parse the results into the format expected by Select2.
        // since we are using custom formatting functions we do not need to alter remote JSON data
        return {
          results: response.result.addresses
        };
      }
    },
    multiple: true,
    allowClear: true,
    width: '450px',
    minimumInputLength: 1,
    minimumResultsForSearch: -1,
    maximumSelectionSize: 200,
    tokenSeparators: [",", ";"],
    createSearchChoice: function(term) {
      // Check if we have an RFC5322 compliant e-mail address:
      if (term.match(/(?:[a-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+\/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])/)) {
        return {"id": term, "fn": term, "address": term};
      }
      return null;
    },
    formatResult: formatComposeResult,
    formatSelection: formatComposeSelection,
    formatSelectionTooBig: function() {
      return 'You\'ve added the maximum contacts allowed, to increase this go to <a href="#">settings</a>';
    },
    selectOnBlur: true
  });

  $('#compose-to').on('change', function(e) {
    }).on('select2-selecting', function(e) {
      composeContactSelected(e);
      console.log('Selecting ' + e.val);
    }).on('select2-removing', function(e) {
      console.log('Removing ' + e.val);
    }).on('select2-removed', function(e) {
      console.log('Removed ' + e.val);
    }).on('select2-blur', function(e){
      console.log('Blur ' + e.val);
  });

}

/* Show Cc, Bcc */
$(document).on('click', '.compose-show-field', function(e) {
  $(this).hide();
  $('#compose-' + $(this).html().toLowerCase() + '-html').show();
});


/* Subject Field */
$('#compose-from').keyup(function (e) {
  var code = (e.keyCode ? e.keyCode : e.which);
  if (code == 9 && $('#compose-subject:focus').val() == '') {
  }
});

$('#compose-subject').on('focus', function() {
  //this.focus();
  //this.select();
});


/* Send & Save */
$(document).on('click', '.compose-action', function(e) {

  e.preventDefault();
  var action = $(this).val();

  if (action == 'send') {
	  var action_url     = mailpile.api.compose_send;
	  var action_status  = 'success';
	  var action_message = 'Your message was sent <a id="status-undo-link" data-action="undo-send" href="#">undo</a>';
  }
  else if (action == 'save') {
	  var action_url     = mailpile.api.compose_save;
	  var action_status  =  'info';
	  var action_message = 'Your message was saved';
  }

	$.ajax({
		url			 : action_url,
		type		 : 'POST',
		data     : $('#form-compose').serialize(),
		dataType : 'json',
	  success  : function(response) {

      if (action == 'send' && response.status == 'success') {
        window.location.href = mailpile.urls.message_sent + response.result.messages[0].mid;
      }
      else {
        statusMessage(response.status, response.message);
      }
	  }
	});
});
MailPile.prototype.view = function(idx, msgid) {
	this.json_get("view", {"idx": idx, "msgid": msgid}, function(data) {
		if ($("#results").length === 0) {
			$("#content").prepend('<table id="results" class="results"><tbody></tbody></table>');
		}
		$("#results").empty();
	});
};