/* Search - select item via clicking */
$(document).on('click', '.pile-results tr.result', function(e) {
  if ($(e.target).attr('type') === 'checkbox') {
    $(e.target).blur();
    Mailpile.pile_action_select($(this));
  }
  else if (e.target.href === undefined &&
    $(this).data('state') !== 'selected' &&
    $(e.target).hasClass('pile-message-tag-name') == false) {
    Mailpile.pile_action_select($(this));    
  }
});


/* Search - unselect search item via clicking */
$(document).on('click', '.pile-results tr.result-on', function(e) {
  if ($(e.target).attr('type') === 'checkbox') {
    $(e.target).prop('checked', false).blur();
    Mailpile.pile_action_unselect($(this));
  }
  else if (e.target.href === undefined &&
    $(this).data('state') === 'selected' && 
    $(e.target).hasClass('pile-message-tag-name') == false) {
    Mailpile.pile_action_unselect($(this));
  }
});


/* Search - Delete Tag via Tooltip */
$(document).on('click', '.pile-tag-delete', function(e) {
  e.preventDefault();
  var tid = $(this).data('tid');
  var mid = $(this).data('mid');
  Mailpile.UI.Tagging.tag_and_update_ui({
    del: tid,
    mid: mid
  }, 'untag', function() {
    $('.pile-message-' + mid + ' .pile-message-tag-' + tid).qtip('hide');
  });
});


/* Search - Searches web for people (currently keyservers only) */
$(document).on('click', '#btn-pile-empty-search-web', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.CryptoFindKeys({
    query: $('#pile-empty-search-terms').html()
  });
});


/* Save Search & Edit Tag */
(function() {
  $(document).on('click', '.bulk-action-save_search', function(e) {
    var template = 'modal-save-search';
    var searchq = ($('#search-query').attr('value') + ' ');
    if (searchq.match(/vfs:/g)) {
      Mailpile.auto_modal({
        url: '{{ U("/settings/mailbox/?path=") }}' + searchq.substring(4),
        method: 'GET',
        reload: true
      });
    }
    else {
      Mailpile.API.with_template(template, function(modal) {
        var mf = Mailpile.UI.show_modal(modal({ terms: searchq }));
        mf.find('#ss-search-terms').attr('value', searchq);
      });
    }
  });
  $(document).on('click', '#modal-save-search .ss-save', function() {
    if ($('#modal-save-search #ss-comment').val() != '') {
      Mailpile.API.filter_post({
        _serialized: $('#modal-save-search').serialize()
      }, function(data) {
        Mailpile.go('/in/saved-search-' + data['result']['id'] + '/');
      });
    }
    else {
      alert('Please name your search!');
    }
    return false;
  });
  function show_settings() {
    $('#modal-full .modal-basic-settings').show();
    $('#modal-full .modal-choose-tag-icon').hide();
    $('#modal-full .modal-choose-tag-color').hide();
    $('#modal-full .tag-edit-technical').hide();
    $('#modal-full .tag-edit-automation').hide();
    $('#modal-full .modal-save-group').show();
  };
  $(document).on('click', '#modal-full .modal-basic-settings-title', show_settings);
  $(document).on('click', '#modal-full .modal-open-choose-tag-color', function() {
    $('#modal-full ul.tag-colors').html(Mailpile.UI.tag_colors_as_lis());
    $('#modal-full .modal-save-group').hide();
    $('#modal-full .modal-basic-settings').hide();
    $('#modal-full .modal-choose-tag-color').show();
  }); 
  $(document).on('click', '#modal-full .modal-open-choose-tag-icon', function() {
    $('#modal-full ul.tag-icons').html(Mailpile.UI.tag_icons_as_lis());
    $('#modal-full .modal-save-group').hide();
    $('#modal-full .modal-basic-settings').hide();
    $('#modal-full .modal-choose-tag-icon').show();
  }); 
  $(document).on('click', '#modal-full .modal-tag-icon-option', function() {
    var icon = $(this).data('icon');
    $('#modal-full input.choose-tag-icon').val(icon);
    $('#modal-full .modal-open-choose-tag-icon'
      ).removeClass().addClass('modal-open-choose-tag-icon').addClass(icon);
    show_settings();
  });
  $(document).on('click', '#modal-full .modal-tag-color-option', function() {
    var name = $(this).data('name');
    var hex = $(this).data('hex');
    $('#modal-full input.choose-tag-color').val(name);
    $('#modal-full .modal-open-choose-tag-icon').css('color', hex);
    $('#modal-full .modal-open-choose-tag-color').css('color', hex);
    show_settings();
  });
  $(document).on('click', '#modal-full .modal-tag-edit-automation', function() {
    $('#modal-full .modal-basic-settings').hide();
    $('#modal-full .modal-choose-tag-icon').hide();
    $('#modal-full .modal-choose-tag-color').hide();
    $('#modal-full .tag-edit-technical').hide();
    $('#modal-full .tag-edit-automation').show();
    $('#modal-full .modal-save-group').show();
  });
  $(document).on('click', '#modal-full .modal-tag-technical', function() {
    $('#modal-full .modal-basic-settings').hide();
    $('#modal-full .modal-choose-tag-icon').hide();
    $('#modal-full .modal-choose-tag-color').hide();
    $('#modal-full .tag-edit-technical').show();
    $('#modal-full .tag-edit-automation').hide();
    $('#modal-full .modal-save-group').show();
  });
})();
