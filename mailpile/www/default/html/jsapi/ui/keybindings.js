Mailpile.keybinding_move_message = function(add_tag) {

  // Has Messages
  var $context = Mailpile.UI.Selection.context('.pile-results tr.is-target');
  var selection = Mailpile.UI.Selection.selected($context);
  if (selection.length) {

    var delete_tags = (($context.find('.pile-results').data("tids") || ""
                        ) + "").split(/\s+/);
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


Mailpile.keybinding_target =  function(direction) {

  var color = this.theme.colors['01-gray-mid'];
  var current  = this.search_target;

  if (this.search_target === 'none') {
    var next = 0;
  }
  else if (this.search_target !== 'none' && direction == 'up') {
    var next = parseInt(current) - 1;
  }
  else if (this.search_target !== 'none' && direction == 'down') {
    var next = parseInt(current) + 1;
  }

  this.search_target = next;

  $('.pile-results tr').eq(current).removeClass('is-target result-hover').find('td.draggable');
  $('.pile-results tr').eq(next).addClass('is-target result-hover').find('td.draggable');
};
