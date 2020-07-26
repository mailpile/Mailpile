// Providing Keybinding/Keyboard shortcuts via Mousetrap
Mailpile.initialize_keybindings = function() {
  Mousetrap.bind("?", function() { Mailpile.display_keybindings(); });
  Mousetrap.bindGlobal("esc", function() {
    $('input[type=text]').blur();
    $('textarea').blur();
  });

  // Map user/system configured bindings
  for (item in Mailpile.keybindings) {
    var keybinding = Mailpile.keybindings[item];
    if (keybinding.global) {
        Mousetrap.bindGlobal(keybinding.keys, keybinding.callback);
    } else {
        Mousetrap.bind(keybinding.keys, keybinding.callback);
    }
  }
};

// ****************************************************************** //
//START OF GREG EDIT //
// ****************************************************************** //

// Problems :
	// 1. When you click to go to the previous element it will stay at the same element / when you click to move to next element it will stay at the same element (switch between j/k k/j)
	// 2. Does not always stop at first element in a thread when pressing j key to go back
	// 3. When you click to move to next email, if the email has a thread, it does not move to thread element 0 it moves instead to thread element 1?
	// 4. Minify and clean up code (put common code into separate functions ? )


var thread_counter = 0;

function j_click() {    
    //Move to previous email in thread
    if ( document.getElementsByClassName("thread-message").length > 0 ){

	if (thread_counter == document.getElementsByClassName("thread-message").length ) {
		thread_counter = thread_counter - 1 ;
		console.log ( "At thread element: ", thread_counter ) ; 
		console.log ( document.getElementsByClassName("thread-message")[thread_counter].click() );
	}

	if (thread_counter == -1 ) {
		// Move to previous email
		if (document.getElementById("previous-message") != null ){
        		console.log ( document.getElementById("previous-message").click() );
			console.log ( "Moving to previous email" );
			thread_counter = 0;
    		}
    		else {
        		console.log ("Please select an email that is not the first email in your inbox, spam, sent");
			thread_counter = 0;
    		}
		
	}
	
	if (thread_counter == 0 ) {
		thread_counter = thread_counter - 1 ;
	}

	if (thread_counter > 0) {
		thread_counter = thread_counter - 1 ;
		console.log ( "At thread element: ", thread_counter ) ; 
		console.log ( document.getElementsByClassName("thread-message")[thread_counter].click() );

	}
	//else move to previous email
	else {
		thread_counter = 0;
		// Move to previous email
		if (document.getElementById("previous-message") != null ){
        		console.log ( document.getElementById("previous-message").click() );
			console.log ( "Moving to previous email" );
    		}
    		else {
        		console.log ("Please select an email that is not the first email in your inbox, spam, sent");
    		}
	}	
    }
    else {
	console.log ( "<- Does not contain a thread!" );
	thread_counter = 0;
	// Move to previous email
	if (document.getElementById("previous-message") != null ){
        	console.log ( document.getElementById("previous-message").click() );
    	}
    	else {
        	console.log ("Please select an email that is not the first email in your inbox, spam, sent");
    	}
    }
}

function k_click() {
    //Move to next email in thread
    if ( document.getElementsByClassName("thread-message").length > 0 ){

	if (thread_counter == -1 ){
		thread_counter = 0;
	}


	if (thread_counter < document.getElementsByClassName("thread-message").length ) {
		console.log("Thread Length: ", document.getElementsByClassName("thread-message").length );
		console.log ( "At thread element: ", thread_counter ) ;
		console.log ( document.getElementsByClassName("thread-message")[thread_counter].click() );
		thread_counter = thread_counter + 1 ;		
	}
	// else move to next email
	else {
		// moving to next email
		thread_counter = 0;
    		// Move to next email
    		if (document.getElementById("next-message") != null ){
        		console.log ( document.getElementById("next-message").click() );
			console.log ( "Moving to next email" );
    		}
    		else {
        		console.log ("Please select an email that is not the last email in your inbox, spam, sent");
    		}
	}
    }
    else {
	console.log ( "Does not contain a thread! ->" );
	thread_counter = 0;
    	// Move to next email
    	if (document.getElementById("next-message") != null ){
        	console.log ( document.getElementById("next-message").click() );
    	}
    	else {
        	console.log ("Please select an email that is not the last email in your inbox, spam, sent");
    	}
    }
}


Mousetrap.bind('k', k_click);
Mousetrap.bind('j', j_click);

// ****************************************************************** //
//END OF GREG EDIT //
// ****************************************************************** //


Mailpile.keybinding_move_messages = function(op, keep_new) {
  // Has Messages
  var $context = Mailpile.UI.Selection.context(".selection-context");
  var selection = Mailpile.UI.Selection.selected($context);
  if (selection.length < 1) {
    console.log('FIXME: Provide helpful / unobstrusive UI feedback that tells a user they hit a keybinding, then fades away');
    return;
  }

  // If there is a button in the UI, prefer to click that to keep behaviours
  // consistent. If not we fall through to direct tagging etc.
  var $button;
  if (op.startsWith('!')) {
    $button = $context.find("a.bulk-action-tag-op[data-op='"+ op.substring(1) +"']");
    op = '';
  }
  else {
    $button = $context.find("a.bulk-action-tag-op[data-tag='"+ op +"']");
  }
  if ($button.length) {
    $button.eq(0).trigger('click');
    return;
  }

  var tids = $context.find(".pile-results").data("tids");
  var delete_tags = ((tids || "") + "").split(/\s+/);
  if (!keep_new) delete_tags.push('new');

  Mailpile.UI.Tagging.tag_and_update_ui({
    add: op,
    del: delete_tags,
    mid: selection,
    context: $context.find('.search-context').data('context')
  }, 'move');

  Mailpile.UI.Selection.select_none($context);
  Mailpile.bulk_actions_update_ui();
};

Mailpile.keybinding_mark_read = function() {
  var $context = Mailpile.UI.Selection.context(".selection-context");
  Mailpile.bulk_action_read(undefined, function() {
    Mailpile.UI.Selection.select_none($context);
  });
};

Mailpile.keybinding_mark_unread = function() {
  var $context = Mailpile.UI.Selection.context(".selection-context");
  Mailpile.bulk_action_unread(undefined, function() {
    Mailpile.UI.Selection.select_none($context);
  });
};

Mailpile.keybinding_undo_last = function() {
  var $undo = $('#notification-bubbles').find('a.notification-undo');
  if ($undo.length) {
    $undo.eq(0).trigger('click'); //closest('.notification-bubble').css({'background': '#770'});
  }
  else {
    // FIXME: Do this yellow thing with classes
    $('#notifications-header').css({'background': '#770'});
    setTimeout(function() {
        $('#notifications-header').css({'background': ''});
    }, 250);
  }
};


Mailpile.keybinding_adjust_viewport = function($last) {
  var $container = $('#content-view, #content-tall-view').eq(0);
  var scroll_top = $container.scrollTop();
  var last_top = $last.position().top - 100;
  $container.animate({ scrollTop: scroll_top + last_top }, 150);

  // Ensure that browser hotkeys focus on the right message too
  $last.find(".subject a").focus();

  // Moving around closes viewed messages
  $('#close-message').trigger('click');
};

Mailpile.keybinding_selection_up = function() {
  var $last = Mailpile.bulk_action_selection_up();
  Mailpile.keybinding_adjust_viewport($last);
};

Mailpile.keybinding_selection_extend = function() {
  var $last = Mailpile.bulk_action_selection_down('keep');
  Mailpile.keybinding_adjust_viewport($last);
};

Mailpile.keybinding_selection_down = function() {
  var $last = Mailpile.bulk_action_selection_down();
  Mailpile.keybinding_adjust_viewport($last);
};

Mailpile.keybinding_select_all_matches = function() {
  Mailpile.bulk_action_select_all();
  Mailpile.select_all_matches();
};

Mailpile.keybinding_reply = function(many) {
  var $context = Mailpile.UI.Selection.context(".selection-context");
  if (!many) {
    var $rbuttons = $context.find('a.message-action-reply-all');
    if ($rbuttons.length) return $rbuttons.eq(0).trigger('click');
  }

  // Which messages are we replying to?
  var selection = Mailpile.UI.Selection.selected($context);
  if (selection.length < 1) {
    Mailpile.keybinding_selection_up();
    selection = Mailpile.UI.Selection.selected($context);
    if (selection.length < 1) return;
  }
  if (!many) selection = [selection[0]];

  Mailpile.Message.DoReply(selection, true);
};

Mailpile.keybinding_forward = function() {
  var $context = Mailpile.UI.Selection.context(".selection-context");

  var $fbuttons = $context.find('a.message-action-forward');
  if ($fbuttons.length) return $fbuttons.eq(0).trigger('click');

  var selection = Mailpile.UI.Selection.selected($context);
  if (selection.length < 1) {
    Mailpile.keybinding_selection_up();
    selection = Mailpile.UI.Selection.selected($context);
    if (selection.length < 1) return;
  }

  Mailpile.Message.DoForward(selection);
};
