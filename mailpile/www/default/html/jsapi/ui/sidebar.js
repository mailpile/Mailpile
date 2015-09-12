Mailpile.UI.Sidebar.SubtagsToggle = function(tid) {

  // Show or Hide
  if (_.indexOf(Mailpile.config.web.subtags_collapsed, tid) > -1) {
    $('#sidebar-tag-' + tid).addClass('show-subtags');
    $('#sidebar-tag-' + tid).find('a.sidebar-tag span.sidebar-tag-expand span').removeClass('icon-arrow-left').addClass('icon-arrow-down');
    $('#sidebar-subtags-' + tid).slideDown('fast');
    var collapsed = _.without(Mailpile.config.web.subtags_collapsed, tid);
  } else {
    $('#sidebar-tag-' + tid).removeClass('show-subtags');
    $('#sidebar-tag-' + tid).find('a.sidebar-tag span.sidebar-tag-expand span').removeClass('icon-arrow-down').addClass('icon-arrow-left');
    $('#sidebar-subtags-' + tid).slideUp('fast');
    Mailpile.config.web.subtags_collapsed.push(tid);
    var collapsed = Mailpile.config.web.subtags_collapsed;
  }

  // Save to Config
  Mailpile.config.web.subtags_collapsed = collapsed;
  Mailpile.API.settings_set_post({ 'web.subtags_collapsed': collapsed }, function(result) { 

  });
};


Mailpile.UI.Sidebar.Sortable = function() {
 $('.sidebar-sortable').sortable({
    placeholder: "sidebar-tags-sortable",
    distance: 13,
    scroll: false,
    opacity: 0.8,
    stop: function(event, ui) {

      var item  = $(ui.item);
      var tid   = item.data('tid');
      var index = parseInt(item.index());

      var get_order = function(index, base) {
        var elem = item.parent().find('li:nth-child(' + index + ')');
        if (elem.length > 0) {
          var display_order = parseFloat(elem.data('display_order'));
          if (!isNaN(display_order)) {
            return display_order;
          }
        }
        return base;
      };

      // Calculate new orders
      var previous  = get_order(index, 0);
      var next      = get_order(index + 2, 1000000);
      var new_order = (parseFloat(previous) + parseFloat(next)) / 2.0;

      alert(index + ': ' + previous + ' .. ' + new_order + ' .. ' + next);

      // Save Tag Order
      var tag_setting = Mailpile.tag_setting(tid, 'display_order', new_order);
      Mailpile.API.settings_set_post(tag_setting, function(result) { 
        // Update Current Element
        $(ui.item).attr('data-display_order', new_order).data('display_order', new_order);
      });
		}
	}).disableSelection();
};


Mailpile.UI.Sidebar.Draggable = function(element) {
  $(element).draggable({
    containment: 'body',
    appendTo: 'body',
    cursor: 'move',
    distance: 15,
    scroll: false,
    revert: false,
    opacity: 1,
    helper: function(event) {
      // FIXME: Helper tooltip assumes only one destination for the drag,
      //        which may not always be true!
      var count = '';
      var selection = Mailpile.UI.Selection.selected('#content');
      if (selection.length >= 1) {
        count = (' {{_("to")|escapejs}} (' +
                 Mailpile.UI.Selection.human_length(selection) + ')');
      }

      var tag = _.findWhere(Mailpile.instance.tags, { tid: $(this).data('tid').toString() });
      var hex = Mailpile.theme.colors[tag.label_color];
      return $('<div class="sidebar-tag-drag ui-widget-header" style="color: ' + hex + '"><span class="' + tag.icon + '"></span> ' + tag.name + count + '</div>');
    }
  });
};


Mailpile.UI.Sidebar.Droppable = function(element, accept) {
  $(element).droppable({
    accept: accept,
    activeClass: 'sidebar-tags-draggable-hover',
    hoverClass: 'sidebar-tags-draggable-active',
    tolerance: 'pointer',
    drop: function(event, ui) {
{#    // What should happen:
      //    - The drop happens on a tag, this tells us which tag to *add*
      //    - If the drop happens on something else... are we just untagging?
      //    - For clarity, require a selection: starting a drag should select
      //    - Can look at ui.draggable.parent() .closest()? to find container.
      //    - Container should be annotated with whatever tags we are looking
      //      at, to facilitate removal so the "move" really is a move.
      //
#}
      // FIXME: This should come from the DOM, not Mailpile.instance
      if (Mailpile.instance.state.command_url == '/message/') {
        var tags_delete = ['inbox'];
      } else {
        var tags_delete = Mailpile.instance.search_tag_ids;
      }

      Mailpile.UI.Tagging.tag_and_update_ui({
        add: $(this).find('a').data('tid'),
        del: tags_delete,
        mid: Mailpile.UI.Selection.selected(ui.draggable)
      }, 'move');
    }
  });
};


Mailpile.UI.Sidebar.OrganizeToggle = function() {
  var new_message = $(this).data('message');
  var old_message = $(this).find('span.text').html();

  // Make Editable
  if ($(this).data('state') === 'done') {

    Mailpile.UI.Sidebar.Sortable();

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
};


Mailpile.UI.Sidebar.TagArchive = function() {
  // FIXME: This should use a modal or styled confirm dialogue and Int. language
  alert('This will mark this tag as "archived" and remove it from your sidebar, you can go edit this in the Tags -> Tag Name -> Settings page at anytime');
  var tid = $(this).parent().data('tid');
  var setting = Mailpile.tag_setting(tid, 'display', 'archive');
  Mailpile.API.settings_set_post(setting, function(result) { 
    Mailpile.notification(result);
    $('#sidebar-tag-' + tid).fadeOut();
  });
};
