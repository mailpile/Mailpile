Mailpile.keybinding_move_message = function(add_tag) {

  // Has Messages
  var selection = Mailpile.UI.Selection.selected('#content');
  if (selection.length) {

    // FIXME: This should come from the DOM, not Mailpile.instance
    var delete_tags = Mailpile.instance.search_tag_ids;
    delete_tags.push('new');

    Mailpile.Tagging.tag_and_update_ui({
      add: add_tag,
      del: delete_tags,
      mid: selection
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
