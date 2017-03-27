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
    Mousetrap.bind(keybinding.keys, keybinding.callback);
  }
};

Mailpile.keybinding_move_message = function(add_tag) {
  // Has Messages
  var $context = Mailpile.UI.Selection.context(".selection-context");
  var selection = Mailpile.UI.Selection.selected($context);
  if (selection.length) {
    var tids = $context.find(".pile-results").data("tids");
    var delete_tags = ((tids || "") + "").split(/\s+/);
    delete_tags.push('new');

    Mailpile.UI.Tagging.tag_and_update_ui({
      add: add_tag,
      del: delete_tags,
      mid: selection,
      context: $context.find('.search-context').data('context')
    }, 'move');
  }
  else {
    console.log('FIXME: Provide helpful / unobstrusive UI feedback that tells a user they hit a keybinding, then fades away');
  }
};

Mailpile.keybinding_view_message = function() {
  var $elem = $('#close-message');
  if ($elem.length > 0) {
    $elem.eq(0).trigger('click');
  }
  else {
    Mailpile.open_selected_thread();
  }
};

Mailpile.keybinding_adjust_viewport = function($last) {
  if ($last.length && !$last.next().next().next().length) {
    $('#pile-more').trigger('click');
  }

  var $container = $('#content-view, #content-tall-view').eq(0);
  var scroll_top = $container.scrollTop();
  var last_top = $last.position().top - 100;
  $container.animate({ scrollTop: scroll_top + last_top }, 150);
};

Mailpile.keybinding_selection_up = function() {
  var selected = Mailpile.UI.Selection.selected('.pile-results');
  var $close = $('#close-message');
  if (($close.length > 0) && (selected.length < 1)) {
    var $target = $('#previous-message');
    if ($target.length > 0) {
      $target.eq(0).trigger('click');
    }
    else $close.trigger('click');
  }
  else {
    var $last = Mailpile.bulk_action_selection_up();
    Mailpile.keybinding_adjust_viewport($last);
  }
};

Mailpile.keybinding_selection_extend = function() {
  var sel = Mailpile.UI.Selection.selected('.pile-results');
  var $msg = $($('#close-message').closest('.pile-message'));

  if (($msg.length > 0) &&
      ((sel.length < 1) || ((sel.length == 1) && (sel[0] == $msg.data('mid')))))
  {
    // If a message is being viewed, we don't actually extend the selection,
    // we just toggle it on/off. This is inconsistent, but less confusing
    // than other options.
    if ($msg.find('input').is(':checked')) {
      Mailpile.pile_action_unselect($msg);
    }
    else {
      Mailpile.pile_action_select($msg);
    }
  }
  else {
    var $last = Mailpile.bulk_action_selection_down('keep');
    Mailpile.keybinding_adjust_viewport($last);
  }
};

Mailpile.keybinding_selection_down = function() {
  var selected = Mailpile.UI.Selection.selected('.pile-results');
  var $close = $('#close-message');
  if (($close.length > 0) && (selected.length < 1)) {
    var $target = $('#next-message');
    if ($target.length > 0) {
      $target.eq(0).trigger('click');
    }
    else $close.eq(0).trigger('click');
  }
  else {
    var $last = Mailpile.bulk_action_selection_down();
    Mailpile.keybinding_adjust_viewport($last);
  }
};
