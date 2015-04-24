
Mailpile.Search = {};

Mailpile.Search.init = function() {
  if (!localStorage.getItem('view_size')) {
    localStorage.setItem('view_size', Mailpile.defaults.view_size);
  }

  Mailpile.Search.PileDisplay(localStorage.getItem('view_size'));

  $.each($('a.change-view-size'), function() {
    if ($(this).data('view_size') == localStorage.getItem('view_size')) {
      $(this).addClass('view-size-selected');
    }
  });

  Mailpile.Search.TagTooltips();
};

Mailpile.Search.events = {
  'click #pile-select-all-action':  'SelectAll',
  'click .bulk-action-archive':     'SelectionArchive',
  'click .bulk-action-trash':       'SelectionTrash',
  'click .bulk-action-spam':        'SelectionSpam',
  'click .bulk-action-unread':      'MarkAsUnread',
  'click .bulk-action-read':        'MarkAsRead',
  'click .bulk-action-tag':         'TagsModalRender',
  'submit #form-tag-picker':        'TagsApply',
  'click .tag-picker-checkbox':     'TagsToggle',
  'click a.change-view-size':       'SetViewSize',
};

Mailpile.Search.TagTooltips = function() {
  $('.pile-message-tag').qtip({
    content: {
      title: false,
      text: function(event, api) {
        var tooltip_data = _.findWhere(Mailpile.instance.tags, { tid: $(this).data('tid').toString() });              
        tooltip_data['mid'] = $(this).data('mid');
        var tooltip_template = _.template($('#tooltip-pile-tag-details').html());
        return tooltip_template(tooltip_data);
      }
    },
    style: {
      classes: 'qtip-thread-crypto',
      tip: {
        corner: 'bottom center',
        mimic: 'bottom center',
        border: 0,
        width: 10,
        height: 10
      }
    },
    position: {
      my: 'bottom center',
      at: 'top left',
      viewport: $(window),
      adjust: {
        x: 7,  y: -4
      }
    },
    show: {
      event: 'click',
      delay: 50
    },
    hide: {
      event: false,
      inactive: 700
    }
  });
}

Mailpile.Search.SetViewSize = function(e) {
  e.preventDefault();
  var current_size = localStorage.getItem('view_size');
  var change_size = $(this).data('view_size');

  // Update Link Selected
  $('a.change-view-size').removeClass('view-size-selected');
  $(this).addClass('view-size-selected');

  Mailpile.Search.PileDisplay(current_size, change_size);
  localStorage.setItem('view_size', change_size);
  Mailpile.API.settings_set_post({ 'web.display_density': change_size }, function(result) {});
};

Mailpile.Search.PileDisplay = function(current, change) {
  if (change) {
    $('#sidebar').removeClass(current).addClass(change);
    $('#pile-results').removeClass(current).addClass(change);
  } else {
    $('#sidebar').addClass(current);
    $('#pile-results').addClass(current);
  }

  setTimeout(function() {
    $('#sidebar').fadeIn('fast');
    $('#pile-results').fadeIn('fast');
  }, 250);
};

Mailpile.Search.TagsModalRender = function() {
  Mailpile.render_modal_tags(); // TODO: This is silly.  
}

Mailpile.Search.SelectionTag = function(action) {
  action["mid"] = Mailpile.messages_cache;
  Mailpile.API.tag_post(action, function(result) {
    Mailpile.notification(result);

    $.each(Mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).fadeOut('fast');
    });

    Mailpile.messages_cache = [];
    Mailpile.Search.UpdateUI();
  });
};

Mailpile.Search.SelectionArchive = function() {
  Mailpile.Search.SelectionTag({ del: 'inbox'});
};

Mailpile.Search.SelectionTrash = function() {
  Mailpile.Search.SelectionTag({ add: 'trash', del: 'new'});
});

Mailpile.Search.SelectionSpam = function() {
  Mailpile.Search.SelectionTag({ add: 'spam', del: 'new'});
});

Mailpile.Search.TagsApply = function(e) {
  e.preventDefault();
  var action = $("button:focus").data('action');

  var add_tags    = [];
  var remove_tags = [];
  var tag_data    = { mid: Mailpile.messages_cache };

  _.each($(this).find('input[name=tid]'), function(val, key) {
    if ($(val).is(':checked') && _.indexOf(Mailpile.tags_cache, $(val).val()) === -1) {
      Mailpile.tags_cache.push($(val).val());
    }
  });

  if (action == 'add') {
    tag_data = _.extend(tag_data, { add: Mailpile.tags_cache });
  } else if (action === 'remove') {
    tag_data = _.extend(tag_data, { del: Mailpile.tags_cache });
  }

  Mailpile.API.tag_post(tag_data, function(result) {

    // Notifications
    Mailpile.notification(result);

    // Add Tags to UI
    if (result.status === 'success') {

      var tag_link_template = _.template($('#template-search-tags-link').html());

      // Affected MID's
      _.each(result.result.msg_ids, function(mid, key) {
        $item = $('#pile-message-' + mid).find('td.subject span.item-tags');
  
        // Add / Remove Tags from UI
        if (action == 'add') {
          _.each(Mailpile.tags_cache, function(tid, key) {
            if ($('#pile-message-tag-' + tid + '-' + mid).length < 1) {
              var tag = _.findWhere(Mailpile.instance.tags, { tid: tid });
              tag['mid'] = mid;
              $item.append(tag_link_template(tag));
            }
          });
        }
        else if (action === 'remove') {
          _.each(Mailpile.tags_cache, function(tid, key) {
            if ($('#pile-message-tag-' + tid + '-' + mid).length >= 1) {
              $('#pile-message-tag-' + tid + '-' + mid).remove();
            };
          });
        }
      });
    }

    $('#modal-full').modal('hide');
  });
});

Mailpile.Search.TagsToggle = function(e) {
  Mailpile.tags_cache = _.without(Mailpile.tags_cache, $(this).val());
});

Mailpile.Search.UpdateUI = function() {
  if (Mailpile.messages_cache.length === 1) {
    var message = '<span id="bulk-actions-selected-count">1</span> ' + $('#bulk-actions-message').data('bulk_selected');
    $('#bulk-actions-message').html(message);
    Mailpile.show_bulk_actions($('.bulk-actions').find('li.hide'));
  } else if (Mailpile.messages_cache.length < 1) { 
    var message = $('#bulk-actions-message').data('bulk_selected_none');
    $('#bulk-actions-message').html(message);
    Mailpile.hide_bulk_actions($('.bulk-actions').find('li.hide'));
	}	else {
	  $('#bulk-actions-selected-count').html(Mailpile.messages_cache.length);
  }
};

Mailpile.Search.MarkAsRead = function() {
  Mailpile.API.tag_post({ del: 'new', mid: Mailpile.messages_cache }, function(result) {
    $.each(Mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).removeClass('in_new');
    });
  });
};

Mailpile.Search.MarkAsUnread = function() {
  Mailpile.API.tag_post({ add: 'new', mid: Mailpile.messages_cache }, function(result) {
    $.each(Mailpile.messages_cache, function(key, mid) {
      $('#pile-message-' + mid).addClass('in_new');
    });
  });
};

Mailpile.Search.Select = function() {
  var target = this.search_target;
  var mid = $('#pile-results tr').eq(target).data('mid');
  Mailpile.bulk_cache_add('messages_cache', mid);
  $('#pile-message-' + mid).addClass('result-on').find('input[type=checkbox]').prop('checked',true);
  Mailpile.Search.UpdateUI();
  return true;
};

Mailpile.Search.Deselect = function() {
  var target = this.search_target;
  var mid = $('#pile-results tr').eq(target).data('mid');
  Mailpile.bulk_cache_remove('messages_cache', mid);
  $('#pile-message-' + mid).removeClass('result-on').find('input[type=checkbox]').prop('checked', false);
  Mailpile.Search.UpdateUI();
  return true;
};

Mailpile.Search.ToggleSelection = function() {
  var target = this.search_target;
  // No Target
  if (target === 'none') {
    var mid = $('#pile-results tr').eq(0).data('mid');
    if ($('#pile-message-' + mid).find('input[type=checkbox]').is(':checked')) {
      Mailpile.pile_action_unselect($('#pile-message-' + mid));
    } else {
      Mailpile.pile_action_select($('#pile-message-' + mid));
    }
  }
  // Has Target
  else {
    var mid = $('#pile-results tr').eq(target).data('mid');
    if ($('#pile-message-' + mid).find('input[type=checkbox]').is(':checked')) {
      Mailpile.bulk_action_deselect_target();
    } else {
      Mailpile.bulk_action_select_target();
    }
  }
  return true;
};

Mailpile.Search.SelectAll = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  $.each(checkboxes, function() {      
    Mailpile.pile_action_select($(this).parent().parent());
  });
  $("#pile-select-all-action").attr('checked','checked');
};

Mailpile.Search.SelectNone = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  $.each(checkboxes, function() {
    Mailpile.pile_action_unselect($(this).parent().parent());
  });
  $("#pile-select-all-action").removeAttr('checked');
};

Mailpile.Search.SelectAllToggle = function(event) {
  if ($(this).attr('checked') === undefined) {
    Mailpile.Search.SelectAll();
  } else {
    Mailpile.Search.SelectNone();
  }
};

Mailpile.Search.SelectInvert = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  $.each(checkboxes, function() {
    if ($(this).is(":checked")) {
      Mailpile.pile_action_unselect($(this).parent().parent());
    } else {
      Mailpile.pile_action_select($(this).parent().parent());
    }
  });
  if (this['messages_cache'].length == checkboxes.length) {
    $("#pile-select-all-action").attr('checked','checked');
  } else if (this['messages_cache'].length == 0) {
    $("#pile-select-all-action").removeAttr('checked');
  }
};

Mailpile.Search.SelectBetween = function() {
  alert('FIXME: Will select messages between two points');
};

Mailpile.Search.CursorUp = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  if (this['messages_cache'].length == 0) {
    Mailpile.pile_action_select($(checkboxes[checkboxes.length-1]).parent().parent());
    return;
  }
  $.each(checkboxes, function() {
    if ($(this).parent().parent().next().children().children("input").is(":checked")) {
      Mailpile.pile_action_select($(this).parent().parent());
    } else {
      Mailpile.pile_action_unselect($(this).parent().parent());
    }
  });
};

Mailpile.Search.CursorDown = function() {
  var checkboxes = $('#pile-results input[type=checkbox]');
  if (this['messages_cache'].length == 0) {
    Mailpile.pile_action_select($(checkboxes[0]).parent().parent());
    return;
  }
  $(checkboxes.get().reverse()).each(function() {
    if ($(this).parent().parent().prev().children().children("input").is(":checked")) {
      Mailpile.pile_action_select($(this).parent().parent());
    } else {
      Mailpile.pile_action_unselect($(this).parent().parent());
    }
  });
};

Mailpile.Search.OpenThread = function() {
  if (this['messages_cache'].length == 1) {
    $("#pile-results input[type=checkbox]:checked").each(function() {
      window.location.href = $(this).parent().parent()
                                    .children(".subject")
                                    .children("a").attr("href");
    });
  }
};

