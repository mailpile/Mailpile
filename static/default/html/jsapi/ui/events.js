$(document).on('click', '.sidebar-tag-expand', function(e) {
  e.preventDefault();
  var tid = $(this).parent().data('tid');
  Mailpile.UI.Sidebar.SubtagsToggle(tid);
});


$(document).on('click', '.is-editing', function(e) {
  e.preventDefault();
});


$(document).on('click', '#button-sidebar-organize', function() {

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
});


$(document).on('click', '.sidebar-tag-archive', function(e) {
  e.preventDefault();
  // FIXME: This should use Int. language
  alert('This will mark this tag as "archived" and remove it from your sidebar, you can go edit this in the Tags -> Tag Name -> Settings page at anytime');
  var tid = $(this).parent().data('tid');
  var setting = Mailpile.tag_setting(tid, 'display', 'archive');
  Mailpile.API.settings_set_post(setting, function(result) { 
    Mailpile.notification(result);
    $('#sidebar-tag-' + tid).fadeOut();
  });
});


$(document).on('click', '#button-sidebar-add', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.AddTag({ location: 'sidebar' });
});


$(document).on('click', '#button-modal-add-tag', function(e) {
  e.preventDefault();
  Mailpile.UI.Modals.AddTagProcess($(this).data('location'));
});