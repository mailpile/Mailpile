$(document).on('click', '.sidebar-tag-expand', function(e) {
  e.preventDefault();
  Mailpile.UI.Sidebar.SubtagsToggle($(this).data('tid'));
});


$(document).on('click', '.is-editing', function(e) {
  e.preventDefault();
});


$(document).on('click', '#button-sidebar-organize', function(e) {
  e.preventDefault();
  Mailpile.UI.Sidebar.OrganizeToggle(this);
});


$(document).on('click', '#button-sidebar-add', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.TagAdd({ location: 'sidebar' });
});


$(document).on('click', '#button-modal-add-tag', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.TagAddProcess($(this).data('location'));
});


$(document).on('click', '.hide-donate-page', function(e) {
  Mailpile.API.settings_set_post({ 'web.donate_visibility': 'False' }, function(e) {
    Mailpile.go('/in/inbox/');
  });
});


$(document).on('click', 'span.checkbox, div.checkbox', function(e) {
  $(this).prev().trigger('click');
});


$(document).on('click', 'a.show-hide, a.do-show', function(e) {
  var $elem = $(this);
  if ($elem.data('done') == 'show') {
    $($elem.data('hide')).slideDown();
    $($elem.data('show')).slideUp();
    if ($elem.hasClass('show-hide')) {
      $elem.data('done', 'hide').removeClass('did-show').addClass('did-hide');
    }
  }
  else {
    $($elem.data('show')).slideDown();
    $($elem.data('hide')).slideUp();
    if ($elem.hasClass('show-hide')) {
      $elem.data('done', 'show').removeClass('did-hide').addClass('did-show');
    }
  }
  if ($elem.data('other')) {
    var msg = $elem.html();
    $elem.html($elem.data('other')).data('other', msg);
  }
  e.preventDefault();
});


// FIXME: this is in the wrong place
Mailpile.auto_modal = function(params) {
  var jhtml_url = Mailpile.API.jhtml_url(params.url);
  if (params.flags) {
    jhtml_url += ((jhtml_url.indexOf('?') != -1) ? '&' : '?') +
                  'ui_flags=' + params.flags.replace(' ', '+');
  }
  $('#modal-full').modal('hide');
  return Mailpile.API.with_template('modal-auto', function(modal) {
    $.ajax({
      url: jhtml_url,
      type: params.method,
      success: function(data) {
        var mf = Mailpile.UI.show_modal(modal({
          data: data,
          icon: params.icon,
          title: params.title,
          header: params.header,
          flags: params.flags
        }));
        if (params.reload && !params.callback) {
          params.callback = function(data) { location.reload(true); };
        }
        if (params.callback) {
          // If there is a callback, we override the form's default behavior
          // and use AJAX instead so our callback can handle the result.
          mf.find('form').submit(function(ev) {
            ev.preventDefault();
            var url = mf.find('form').attr('action');
            if ('{{ config.sys.http_path }}' != '') url = url.substring('{{ config.sys.http_path }}'.length);
            url = '{{ config.sys.http_path }}/api/0' + url;
            $.ajax({
              type: "POST",
              url: url,
              data: mf.find('form').serialize(),
              // FIXME: Errors are not handled at all here!
              success: function(data) {
                mf.modal('hide');
                return params.callback(data);
              }
            });
            return false;
          });
        }
      }
    });
  }, undefined, params.flags, 'Unsafe');
};


$(document).on('click', '.auto-modal', function(e) {
  var elem = $(this);
  var title = elem.data('title') || elem.attr('title');
  Mailpile.auto_modal({
    url: this.href,
    method: elem.data('method') || 'GET',
    title: title,
    icon: elem.data('icon'),
    flags: elem.data('flags'),
    header: elem.data('header'),
    reload: elem.data('reload') || elem.hasClass('auto-modal-reload')
  });
  return false;
});


$(document).on('click', 'a.ok-got-it', function(e) {
  var $elem = $(this);
  var cfg_variable = $elem.data('variable');
  var dom_remove = $elem.data('remove');
  var cleanup = function() {
    if (dom_remove) $('.' + dom_remove).remove();
    $elem.closest('#modal-full').modal('hide');
  };
  if (cfg_variable) {
    var args = {};
    args[cfg_variable] = false;
    Mailpile.API.settings_set_post(args, cleanup);
  }
  else cleanup();
  return false;
});
