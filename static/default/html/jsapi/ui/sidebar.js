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
      var count = '';
      if (Mailpile.messages_cache.length > 1) {
        count = ' to (' + Mailpile.messages_cache.length + ')';
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
    over: function(event, ui) {
      var tid = $(this).find('a').data('tid');
      setTimeout(function() {
        //Mailpile.UI.SidebarSubtagsToggle(tid, 'open');
      }, 500);
    },
    out: function(event, ui) {
      var tid = $(this).find('a').data('tid');
      setTimeout(function() {
        //Mailpile.UI.SidebarSubtagsToggle(tid, 'close');
      }, 1000);
    },
    drop: function(event, ui) {
  
      var tid = $(this).find('a').data('tid');
  
      // Add MID to Cache
      Mailpile.bulk_cache_add('messages_cache', ui.draggable.parent().data('mid'));
  
      // Add / Delete
      if (Mailpile.instance.state.command_url == '/message/') {
        var tags_delete = ['inbox'];
      } else {
        var tags_delete = Mailpile.instance.search_tag_ids;
      }
  
      Mailpile.API.tag_post({ add: tid, del: tags_delete, mid: Mailpile.messages_cache}, function(result) {
  
        // Show
        Mailpile.notification(result);
  
        // Update Pile View
        if (Mailpile.instance.state.command_url == '/search/') {
          $.each(Mailpile.messages_cache, function(key, mid) {
            $('#pile-message-' + mid).fadeOut('fast');
          });

          // Empty Bulk Cache
          Mailpile.messages_cache = [];

          // Update Bulk UI
          Mailpile.bulk_actions_update_ui();

          // Hide Collapsible
          Mailpile.UI.Sidebar.SubtagsToggle(tid, 'close');

        } else {
          // FIXME: this action is up for discussion
          // Github Issue - https://github.com/pagekite/Mailpile/issues/794
          window.location.href = '/in/inbox/';
        }
      });
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
