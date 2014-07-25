Mailpile.ui_sidebar_toggle_subtags = function(tid, state) {
  $.each($('.subtag-of-' + tid), function(key, item) {
    if ($(this).css('display') === 'none' && state === 'open') {
      $(this).removeClass('hide');
    }
    else if ($(this).css('display') === 'list-item' && state === 'close') {
      $(this).addClass('hide');
    }
    else if (state === 'toggle') {
      if ($(this).css('display') === 'none') {
        $(this).removeClass('hide');
      }
      else {
        $(this).addClass('hide');
      }
    }
  });
};


$(document).on('click', '.icon-tags', function(e) {
  e.preventDefault();
  var tid = $(this).parent().data('tid');
  Mailpile.ui_sidebar_toggle_subtags(tid, 'toggle');
});


$(document).on('click', '.is-editing', function(e) {
  e.preventDefault();
});


$(document).on('click', '.button-sidebar-edit', function() {

  var new_message = $(this).data('message');
  var old_message = $(this).find('span.text').html();

  // Make Editable
  if ($(this).data('state') === 'done') {

    // Disable Drag & Drop
    $('a.sidebar-tag').draggable({ disabled: true });
    
    // Update Cursor Make Links Not Work
    $('.sidebar-sortable li').addClass('is-editing');

    // Hide Notification & Subtags
    $('.sidebar-notification').hide();
    $('.sidebar-subtag').hide();

    // Add Minus Button
    $.each($('.sidebar-tag'), function(key, value) {
      $(this).append('<span class="sidebar-tag-archive icon-minus"></span>');
    });

    // Update Edit Button
    $(this).data('message', old_message).data('state', 'editing');
    $(this).find('span.icon').removeClass('icon-settings').addClass('icon-checkmark');

  } else {

    // Enable Drag & Drop
    $('a.sidebar-tag').draggable({ disabled: false });    

    // Update Cursor Make Links Not Work
    $('.sidebar-sortable li').removeClass('is-editing');

    // Show Notification / Hide Minus Button
    $('.sidebar-notification').show();
    $('.sidebar-tag-archive').remove();

    // Update Edit Button
    $(this).data('message', old_message).data('state', 'done');
    $(this).find('span.icon').removeClass('icon-checkmark').addClass('icon-settings');
  }

  $(this).find('span.text').html(new_message);
});


$(document).on('click', '.sidebar-tag-archive', function(e) {
  e.preventDefault();
  // FIXME: This should use Int. language
  alert('This will mark this tag as "archived" and remove it from your sidebar, you can go edit this in the Tags -> Tag Name -> Settings page at anytime');
  var tid = $(this).parent().data('tid');
  Mailpile.tag_update(tid, 'display', 'archive', function() {
    $('#sidebar-tag-' + tid).fadeOut();
  });
});


$(document).ready(function() {

  // Drag Sort Tag Order
	$( ".sidebar-sortable" ).sortable({
		placeholder: "sidebar-tags-sortable",
    distance: 13,
    scroll: false,
    opacity: 0.8,
		stop: function(event, ui) {

      var get_order = function(index, base) {
        $elem = $('.sidebar-sortable li:nth-child(' + index + ')');
        if ($elem.length) {
          var display_order = parseFloat($elem.data('display_order'));
          if (!isNaN(display_order)) {
            return display_order;
          }
        }
        return base;
      };

      var tid   = $(ui.item).data('tid');
			var index = $(ui.item).index();

      // Calculate new orders
      var previous  = get_order(index, 0);
      var next      = get_order((parseInt(index) + 2), 1000000);
      var new_order = (parseFloat(previous) + parseFloat(next)) / 2;

      // Save Tag Order
      Mailpile.tag_update(tid, 'display_order', new_order, function() {

        // Update Current Element
        $(ui.item).attr('data-display_order', new_order).data('display_order', new_order);
      });
		}
	}).disableSelection();
  

  // Drag Tags to Search Messages
  $('a.sidebar-tag').draggable({
    containment: "#container",
    appendTo: 'body',
    cursor: 'move',
    distance: 15,
    scroll: false,
    revert: false,
    opacity: 1,
    helper: function(event) {
      var count = '';
      if (Mailpile.messages_cache.length > 1) {
        count = ' to (' + Mailpile.messages_cache.length + ')';
      }

      var tag = _.findWhere(Mailpile.instance.tags, { tid: $(this).data('tid').toString() });
      var hex = Mailpile.theme.colors[tag.label_color];
      return $('<div class="sidebar-tag-drag ui-widget-header" style="color: ' + hex + '"><span class="' + tag.icon + '"></span> ' + tag.name + count + '</div>');
    }
  });


  $('#pile-results tr').droppable({
    accept: 'a.sidebar-tag',
    hoverClass: 'result-hover',
    tolerance: 'pointer',
    drop: function(event, ui) {

      // Update Cache
      Mailpile.bulk_cache_add('messages_cache', $(event.target).data('mid'));

      // Save Update
      Mailpile.tag_add_delete(ui.draggable.data('tid'), '', Mailpile.messages_cache, function() {

        var tag = _.findWhere(Mailpile.instance.tags, { tid: ui.draggable.data('tid').toString() });
        var hex = Mailpile.theme.colors[tag.label_color];
        var updated = [];

        // Update Multiple Selected Messages
        if (Mailpile.messages_cache.length > 0) {
          $.each(Mailpile.messages_cache, function(key, mid) {
            updated.push(mid);
            $('#pile-message-' + mid).find('td.subject span.item-tags').append('<span class="pile-message-tag" style="color: ' + hex + ';"><span class="pile-message-tag-icon ' + tag.icon + '"></span> <span class="pile-message-tag-name">' + tag.name + '</span></span>');
          });
        }
      });
    }
  });

});