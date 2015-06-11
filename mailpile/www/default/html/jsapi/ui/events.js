$(document).on('click', '.sidebar-tag-expand', function(e) {
  e.preventDefault();
  var tid = $(this).parent().data('tid');
  Mailpile.UI.Sidebar.SubtagsToggle(tid);
});


$(document).on('click', '.is-editing', function(e) {
  e.preventDefault();
});


$(document).on('click', '#button-sidebar-organize', function(e) {
  e.preventDefault();
  Mailpile.UI.Sidebar.OrganizeToggle();
});


$(document).on('click', '.sidebar-tag-archive', function(e) {
  e.preventDefault();
  Mailpile.UI.Sidebar.TagArchive();
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
    window.location.href = '/in/inbox/';
  });
});


$(document).on('click', 'span.checkbox, div.checkbox', function(e) {
  $(this).prev().trigger('click');
});


$(document).on('click', '.auto-modal', function(e) {
  var elem = $(this);
  var jhtml_url = Mailpile.API.jhtml_url(this.href);
  var method = elem.data('method') || 'GET';
  var title = elem.attr('title');
  var icon = elem.data('icon');
  var flags = elem.data('flags');
  var header = elem.data('header');
  if (flags) {
    jhtml_url += ((jhtml_url.indexOf('?') != -1) ? '&' : '?') + 'ui_flags=' + flags.replace(' ', '+');
  }
  Mailpile.API.with_template('modal-auto', function(modal) {
    $.ajax({
      url: jhtml_url,
      type: method,
      success: function(data) {
        var mf = $('#modal-full').html(modal({
          data: data,
          icon: icon,
          title: title,
          header: header,
          flags: flags
        }));
        mf.modal(Mailpile.UI.ModalOptions);
      }
    });
  }, undefined, flags);
  return false;
});
