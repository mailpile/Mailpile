Mailpile.keybinding_move_message = function(add_tag) {

  // Has Messages
  if (this.messages_cache.length) {

    var delete_tags = Mailpile.instance.search_tag_ids;
    delete_tags.push('new');

    // Add / Delete
    Mailpile.API.tag_post({ add: add_tag,del: delete_tags, mid: Mailpile.messages_cache}, function(result) {

      Mailpile.notification(result);

      // Update Pile View
      $.each(Mailpile.messages_cache, function(key, mid) {
        $('#pile-message-' + mid).fadeOut('fast');
      });

      // Empty Bulk Cache
      Mailpile.messages_cache = [];

      // Update Bulk UI
      Mailpile.bulk_actions_update_ui();
    });    
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

  $('#pile-results tr').eq(current).removeClass('is-target result-hover').find('td.draggable');
  $('#pile-results tr').eq(next).addClass('is-target result-hover').find('td.draggable');
};


/* Keybinding - FIXME: will allow holding shift key to select items in list between 
   a previous selected point + new target OR two select items */
Mailpile.keybinding_shift_router = function() {

  if (this.instance.state.command_url === '/search/') {
    console.log('Shift Search: check for selected items');
  }
  else if (this.instance.state.command_url === '/search/') {
    console.log('Shift Search: check for selected items');
  }

};