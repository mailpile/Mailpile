/* Search - select item via clicking */
$(document).on('click', '#pile-results tr.result', function(e) {
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
$(document).on('click', '#pile-results tr.result-on', function(e) {
  if ($(e.target).attr('type') === 'checkbox') {
    $(e.target).val('').attr('checked', false).blur();
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
  Mailpile.API.tag_post({ del: tid, mid: mid }, function(result) {
    Mailpile.notification(result);
    $('#pile-message-tag-' + tid + '-' + mid).qtip('hide').remove();
  });
});


/* Search - Searches web for people (currently keyservers only) */
$(document).on('click', '#btn-pile-empty-search-web', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.CryptoFindKeys({
    query: $('#pile-empty-search-terms').html()
  });
});


/* Save Search */
(function() {
  $(document).on('click', '.bulk-action-save_search', function(e) {
    var template = 'modal-save-search';
    var searchq = ($('#search-query').attr('value') + ' ');
    if (searchq.match(/vfs:/g)) {
      template = 'modal-save-mailbox';
    }
    Mailpile.API.with_template(template, function(modal) {
      mf = $('#modal-full').html(modal({
        terms: searchq,
        icons: Mailpile.UI.tag_icons_as_lis(),
        colors: Mailpile.UI.tag_colors_as_lis()
      }));
      mf.find('#ss-search-terms').attr('value', searchq);
      mf.modal(Mailpile.UI.ModalOptions);
    });
  });
  $(document).on('click', '#modal-save-search .ss-save', function() {
    if ($('#modal-save-search #ss-comment').attr('value') != '') {
      Mailpile.API.filter_post({
        _serialized: $('#modal-save-search').serialize()
      }, function(data) {
        window.location.href = ('{{ config.sys.http_path }}/in/saved-search-'
                                + data['result']['id'] + '/');
      });
    };
    return false;
  });
  function show_settings() {
    $('#modal-save-search .save-search-settings').show();
    $('#modal-save-search .save-search-choose-icon').hide();
    $('#modal-save-search .save-search-choose-color').hide();
    $('#modal-save-search .ss-save-group').show();
  };
  $(document).on('click', '#modal-save-search .ss-settings-title', show_settings);
  $(document).on('click', '#modal-save-search .ss-choose-color', function() {
    $('#modal-save-search .ss-save-group').hide();
    $('#modal-save-search .save-search-settings').hide();
    $('#modal-save-search .save-search-choose-color').show();
  }); 
  $(document).on('click', '#modal-save-search .ss-choose-icon', function() {
    $('#modal-save-search .ss-save-group').hide();
    $('#modal-save-search .save-search-settings').hide();
    $('#modal-save-search .save-search-choose-icon').show();
  }); 
  $(document).on('click', '#modal-save-search .modal-tag-icon-option', function() {
    var icon = $(this).data('icon');
    $('#modal-save-search .ss-tag-icon').val(icon);
    $('#modal-save-search .ss-choose-icon').removeClass().addClass('ss-choose-icon').addClass(icon);
    show_settings();
  });
  $(document).on('click', '#modal-save-search .modal-tag-color-option', function() {
    var name = $(this).data('name');
    var hex = $(this).data('hex');
    $('#modal-save-search .ss-tag-color').val(name);
    $('#modal-save-search .ss-choose-icon').css('color', hex);
    $('#modal-save-search .ss-choose-color').css('color', hex);
    show_settings();
  });
})();


/* Edit Tag (from search result view) */
(function() {
  $(document).on('click', '.bulk-action-edit_tag', function(e) {
    var template = 'modal-edit-tag';
    Mailpile.API.with_template(template, function(modal) {
      mf = $('#modal-full').html(modal({
        icons: Mailpile.UI.tag_icons_as_lis(),
        colors: Mailpile.UI.tag_colors_as_lis()
      }));
      mf.modal(Mailpile.UI.ModalOptions);
    });
  });

  /* FIXME */
})();

