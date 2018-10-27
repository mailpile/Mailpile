/* Search - Bulk Select / Unselect All */
$(document).on('click', '#pile-select-all-action', function(e) {
  var $checkbox = $(this);
  var $results = $checkbox.closest('.selection-context')
                          .find('.pile-results .pile-message');
  if ($checkbox.is(':checked')) {
    // Going from unchecked -> checked
    $results.each(function(i, result) {
      Mailpile.pile_action_select($(result), "partial");
    });
  }
  else {
    // Going from checked -> unchecked
    $checkbox.val('');
    $results.each(function(i, result) {
      Mailpile.pile_action_unselect($(result), "partial");
    });
  }
  Mailpile.bulk_actions_update_ui();
  return true;
});


/* Search - Bulk Action - Tag */
$(document).on('click', '.bulk-action-tag', function() {
  Mailpile.render_modal_tags(this);
});

/* Search - Bulk Action - Toggle attribute (Tag) */
$(document).on('click', '.bulk-action-tag-op', function() {
  var $elem = $(this);
  var tag = (($elem.data('tag') || "") + "").split(/\s+/);
  var op = $elem.data('op');
  var desc = $elem.data('ui');

  var $context = Mailpile.UI.Selection.context($elem);
  var args = {
    mid: Mailpile.UI.Selection.selected($context),
    context: $context.find('.search-context').data('context')
  };

  if (op == "toggle") {
    if ($elem.data('mode') != 'untag') {
      args.add = tag;
      desc = desc || 'tag';
    } else {
      args.del = tag;
      desc = desc || 'untag';
    }
  }
  else if (op == "move") {
    args.add = tag;
    args.del = (($context.find('.pile-results').data("tids") || ""
                 ) + "").split(/\s+/);
  }
  else if (op == "tag") {
    args.add = tag;
    if ($elem.data('untag')) args.del = $elem.data('untag').split(/\s+/);
  }
  else if (op == "untag") {
    args.del = (($context.find('.pile-results').data("tids") || ""
                 ) + "").split(/\s+/);
    desc = desc || 'untag';
  }
  else if (op == "archive") {
    args.del = ['type:inbox', 'type:tag', 'type:attribute', 'type:sent'];
    desc = desc || 'archive';
  }

  if (!desc) desc = (args.del) ? 'move' : 'tag';
  Mailpile.UI.Tagging.tag_and_update_ui(args, desc);
});

