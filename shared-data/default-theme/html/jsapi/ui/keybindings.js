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
