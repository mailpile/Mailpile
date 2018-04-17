Mailpile.UI.Sidebar.SubtagsToggle = function(tid) {
  // Strategy: assume whatever is in the DOM is correct and take actions
  // based on that (after all, that's what the users sees). However, we
  // then send config updates to the backend for persistence.

  var $toggle = $('.sidebar-tag-expand[data-tid='+ tid +']');
  var $subtags = $('.subtag-of-' + tid);

  var is_collapsed = $toggle.data('collapsed');
  if (is_collapsed == 'False') is_collapsed = false;

  if (is_collapsed) {
    $toggle.find('span').removeClass('icon-arrow-right').addClass('icon-arrow-down');
    $toggle.data('collapsed', 'False');
    $subtags.slideDown('fast');
  }
  else {
    $toggle.find('span').addClass('icon-arrow-right').removeClass('icon-arrow-down');
    $toggle.data('collapsed', 'True');
    $subtags.slideUp('fast');
  }

  var collapsed = [];
  $('.sidebar-tag-expand').each(function(k, v) {
    var $v = $(v);
    var is_collapsed = $v.data('collapsed');
    if (is_collapsed == 'False') is_collapsed = false;
    if (is_collapsed) collapsed.push($v.data('tid'));
  });
  if (collapsed.length < 1) collapsed = ['_none_'];

  Mailpile.API.settings_set_post({
    'web.subtags_collapsed': collapsed
  }, function(result) {
    // Nothing
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
    containment: 'window',
    appendTo: 'body',
    handle: '.name',
    cursor: 'move',
    cursorAt: { left: 15, bottom: -10 },
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

      var $elem = $(this);
      var tid = $elem.data('tid').toString();
      var hex = Mailpile.theme.colors[$elem.data('color')];
      var icon = $elem.data('icon');
      var name = $elem.find('.name').html();
      return $('<div class="sidebar-tag-drag ui-widget-header" style="color: '
               + hex + '"><span class="' + icon + '"></span> '
               + name + count + '</div>');
    },
    start: function() {
      Mailpile.ui_in_action += 1;
    },
    stop: function() {
      setTimeout(function() {
        Mailpile.ui_in_action -= 1;
        console.log("Decremented ui_in_action: " + Mailpile.ui_in_action);
      }, 250);
    }
  });
};


Mailpile.UI.Sidebar.Droppable = function(element, accept) {
  $(element).droppable({
    accept: accept,
    activeClass: 'sidebar-tags-draggable-hover',
    hoverClass: 'sidebar-tags-draggable-active',
    tolerance: 'pointer',
    greedy: true,
    drop: function(event, ui) {
      // This is necessary to prevent drops on elements that aren't visible.
      var t = $(this).droppable("widget")[0];
      var e = document.elementFromPoint(event.clientX, event.clientY);
      while (e && (t !== e)) {
        e = e.parentNode;
      }
      if (t !== e) return false;

      console.log("Dropped on sidebar!");

{#    // What should happen:
      //    - The drop happens on a tag, this tells us which tag to *add*
      //    - If the drop happens on something else... are we just untagging?
      //    - For clarity, require a selection: starting a drag should select
      //    - Can look at ui.draggable.parent() .closest()? to find container.
      //    - Container should be annotated with whatever tags we are looking
      //      at, to facilitate removal so the "move" really is a move.
      // #}

      var $context = Mailpile.UI.Selection.context(ui.draggable);
      var tags_delete = (($context.find('.pile-results').data("tids") || ""
                          ) + "").split(/\s+/);
      Mailpile.UI.Tagging.tag_and_update_ui({
        add: $(this).find('a').data('tid'),
        del: tags_delete,
        mid: Mailpile.UI.Selection.selected($context),
        context: $context.find('.search-context').data('context')
      }, 'move');
    }
  });
};


Mailpile.UI.Sidebar.OrganizeToggle = function(elem) {
  var $elem = $(elem);
  var new_message = $elem.data('message');
  var old_message = $elem.find('span.text').html();

  // Make Editable
  if ($elem.data('state') != 'editing') {
    Mailpile.ui_in_action += 1;
    Mailpile.UI.Sidebar.Sortable();

    // Disable Drag & Drop
    $('a.sidebar-tag').draggable({ disabled: true });

    // Display tags that are normally hidden
    $('li.sidebar-tag.hide').addClass('should-hide').slideDown();
    $('li.sidebar-tag.hide a.sidebar-tag').css({'opacity': 0.5});

    // Update Cursor Make Links Not Work
    $('.sidebar-sortable li').addClass('is-editing');

    // Hide Notification & Subtags
    $('a.sidebar-tag .notification').hide();
    $('li.sidebar-tag .sidebar-tag-expand').hide();
    $('.sidebar-subtag').slideUp();

    // Add Settings Button
    $.each($('li.sidebar-tag'), function(key, value) {
      var slug = $(this).data('slug');
      $(this).append(
        '<a class="sidebar-tag-settings auto-modal auto-modal-reload"' +
        ' title="Edit: ' + slug + '"' +
        ' href="/tags/edit.html?only='+slug+'">' +
        '<span class="icon-settings"></span></a>');
    });

    // Update Edit Button
    $elem.data('state', 'editing');
    $elem.find('span.icon').removeClass('icon-settings').addClass('icon-checkmark');

  } else {

    Mailpile.ui_in_action -= 1;

    // Enable Drag & Drop
    $('a.sidebar-tag').draggable({ disabled: false });

    // Update Cursor Make Links Work
    $('.sidebar-sortable li').removeClass('is-editing');

    // Show Notification / Remove Settings Button
    $('a.sidebar-tag .notification').show();
    $('li.sidebar-tag .sidebar-tag-expand').show();
    $('.sidebar-tag-settings').remove();

    // Hide tags that are normally hidden
    $('li.sidebar-tag.should-hide').slideUp();

    // Update Edit Button
    $elem.data('state', 'done');
    $elem.find('span.icon').removeClass('icon-checkmark').addClass('icon-settings');
  }

  $elem.data('message', old_message)
  $elem.find('span.text').html(new_message);
};


// Register update functions
Mailpile.UI.content_setup.push(function($content) {
  Mailpile.UI.Sidebar.Draggable(
    $content.find('.sidebar-tags-draggable a.sidebar-tag'));
  Mailpile.UI.Sidebar.Droppable(
    $content.find('.sidebar-tags-draggable'),
   'td.draggable, td.avatar, div.thread-draggable');
});
