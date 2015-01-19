/* Tag - Tag Add */
Mailpile.tag_add = function(tag_add, mids, complete) {
  $.ajax({
	  url			 : Mailpile.api.tag,
	  type		 : 'POST',
	  data     : {
      add: tag_add,
      mid: mids
    },
	  dataType : 'json',
    success  : function(response) {
      if (response.status == 'success') {
       complete(response.result);       
      } else {
        Mailpile.notification(response);
      }
    }
  });
};


/* Tag - Make Setting Data */
Mailpile.tag_setting = function(tid, setting, value) {
  var key = 'tags.' + tid + '.' + setting;
  var setting = {};
  setting[key] = value;
  return setting;
};


$(document).on('click', '#button-tag-change-icon', function() {

  var icons_html = '';
  $.each(Mailpile.theme.icons, function(key, icon) {
    icons_html += '<li class="modal-tag-icon-option ' + icon + '" data-icon="' + icon + '"></li>';
  });

  var modal_template = _.template($("#modal-tag-icon-picker").html());
  $('#modal-full').html(modal_template({ icons: icons_html }));
  $('#modal-full').modal(Mailpile.UI.ModalOptions);
});


$(document).on('click', '.modal-tag-icon-option', function() {

  var tid  = $('#data-tag-tid').val();
  var old  = $('#data-tag-icon').val();
  var icon = $(this).data('icon');

  var setting = Mailpile.tag_setting(tid, 'icon', icon);
  Mailpile.API.settings_set_post(setting, function(result) { 

    Mailpile.notification(result);

    // Update Sidebar
    $('#sidebar-tag-' + tid).find('span.icon').removeClass(old).addClass(icon);

    // Update Tag Editor
    $('#data-tag-icon').val(icon);
    $('#tag-editor-icon').removeClass().addClass(icon);
    $('#modal-full').modal('hide');
  });
});


$(document).on('click', '#button-tag-change-label-color', function(e) {
  
  var sorted_colors =  _.keys(Mailpile.theme.colors).sort();
  var colors_html = '';
  $.each(sorted_colors, function(key, name) {
    var hex = Mailpile.theme.colors[name];
    colors_html += '<li><a href="#" class="modal-tag-color-option" style="background-color: ' + hex + '" data-name="' + name + '" data-hex="' + hex + '"></a></li>';
  });

  var modal_html = $("#modal-tag-color-picker").html();
  var modal_template = _.template(modal_html);
  $('#modal-full').html(modal_template({ colors: colors_html }));
  $('#modal-full').modal(Mailpile.UI.ModalOptions);
});


$(document).on('click', '.modal-tag-color-option', function(e) {

  var tid   = $('#data-tag-tid').val();
  var old   = $('#data-tag-label-color').val();
  var name = $(this).data('name');
  var hex = $(this).data('hex');

  var setting = Mailpile.tag_setting(tid, 'label_color', name);
  Mailpile.API.settings_set_post(setting, function(result) { 

    Mailpile.notification(result);

    // Update Sidebar
    $('#sidebar-tag-' + tid).find('span.icon').css('color', hex);

    // Update Tag Editor
    $('#data-tag-label-color').val(name);
    $('#tag-editor-icon').css('color', hex);
    $('#modal-full').modal('hide');
  });
});


/* API - Tag Add */
$(document).on('submit', '#form-tag-add', function(e) {
  e.preventDefault();
  var tag_data = $('#form-tag-add').serialize();
  Mailpile.API.tags_add_post(tag_data, function() {
    window.location.href = '/tags/edit.html?only=' + $('#data-tag-add-slug').val();
  });
});


/* Tag - Delete Tag */
$(document).on('click', '#button-tag-delete', function(e) {
  if (confirm('Sure you want to delete this tag?') === true) { 
    Mailpile.API.tags_delete_post({ tag: $('#data-tag-add-slug').val() }, function(response) {
      window.location.href = '/tags/';
    }, 'POST');
  }
});


/* Tag - Toggle Archive */
$(document).on('click', '#button-tag-toggle-archive', function(e) {
  var new_message = $(this).data('message');
  var old_message = $(this).html();
  $(this).data('message', old_message);
  $(this).html(new_message);
  if ($('#tags-archived-list').hasClass('hide')) {
    $('#tags-archived-list').removeClass('hide');
  } else {
    $('#tags-archived-list').addClass('hide');    
  }
});


/* Tag - Update the Name & Slug */
$(document).on('blur', '#data-tag-add-tag', function(e) {
  var settings = {};
  settings['tags.' + $('#data-tag-tid').val() + '.name'] = $(this).val();
  settings['tags.' + $('#data-tag-tid').val() + '.slug'] = $('#data-tag-add-slug').val();
  Mailpile.API.settings_set_post(settings, function(result) {
    Mailpile.notification(result);
  });
});


/* Tag - Update the Slug */
$(document).on('blur', '#data-tag-add-slug', function(e) {
  var setting = Mailpile.tag_setting($('#data-tag-tid').val(), 'slug', $('#data-tag-add-slug').val());
  Mailpile.API.settings_set_post(setting, function(result) { 
    Mailpile.notification(result);
  });
});


/* Tag - Update (multiple attribute events) */
$(document).on('change', '#data-tag-display', function(e) {
  var setting = Mailpile.tag_setting($('#data-tag-tid').val(), 'display', $(this).val());
  Mailpile.API.settings_set_post(setting, function(result) {
    Mailpile.notification(result);
  });  
});


/* Tag - Update parent */
$(document).on('change', '#data-tag-parent', function(e) {
  var setting = Mailpile.tag_setting($('#data-tag-tid').val(), 'parent', $(this).val());
  Mailpile.API.settings_set_post(setting, function(result) {
    Mailpile.notification(result);
  });  
});


/* Tag - Update Label */
$(document).on('change', '#data-tag-label', function(e) {
  var label = 'false';
  if ($(this).is(':checked')) {
    label = 'true';
  }
  var setting = Mailpile.tag_setting($('#data-tag-tid').val(), 'label', label);
  Mailpile.API.settings_set_post(setting, function(result) {
    Mailpile.notification(result);
  });
});

