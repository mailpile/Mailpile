/* Pile - Tag Add */
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
        Mailpile.notification(response.status, response.message);
      }
    }
  });
};


Mailpile.tag_add_delete = function(tag_add, tag_del, mids, complete) {
  $.ajax({
	  url			 : Mailpile.api.tag,
	  type		 : 'POST',
	  data     : {
      add: tag_add,
      del: tag_del,
      mid: mids
    },
	  dataType : 'json',
    success  : function(response) {
      if (response.status == 'success') {
        complete(response.result);
      } else {
        Mailpile.notification(response.status, response.message);
      }
    }
  });
};


Mailpile.tag_update = function(tid, setting, value, complete) {

  // Prep Update Value
  var key = 'tags.' + tid + '.' + setting;
  var setting = {};
  setting[key] = value;

  $.ajax({
	  url			 : Mailpile.api.tag_update,
	  type		 : 'POST',
	  data     : setting,
	  dataType : 'json',
    success  : function(response) {
      if (response.status == 'success') {
        complete(response.result);
      } else {
        Mailpile.notification(response.status, response.message);
      }
    }
  });
};


$(document).on('click', '#button-tag-change-icon', function() {

  var icons_html = '';
  $.each(Mailpile.theme.icons, function(key, icon) {
    icons_html += '<li class="modal-tag-icon-option ' + icon + '" data-icon="' + icon + '"></li>';
  });

  var modal_html = $("#modal-tag-icon-picker").html();
  $('#modal-full').html(_.template(modal_html, { icons: icons_html }));
  $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
});


$(document).on('click', '.modal-tag-icon-option', function() {

  var tid  = $('#data-tag-tid').val();
  var old  = $('#data-tag-icon').val();
  var icon = $(this).data('icon');

  Mailpile.tag_update(tid, 'icon', icon, function() {

    // Update Sidebar
    $('#sidebar-tag-' + tid).find('span.sidebar-icon').removeClass(old).addClass(icon);

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
  $('#modal-full').html(_.template(modal_html, { colors: colors_html }));
  $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
});


$(document).on('click', '.modal-tag-color-option', function(e) {

  var tid   = $('#data-tag-tid').val();
  var old   = $('#data-tag-label-color').val();
  var name = $(this).data('name');
  var hex = $(this).data('hex');

  Mailpile.tag_update(tid, 'label_color', name, function() {

    // Update Sidebar
    $('#sidebar-tag-' + tid).find('span.sidebar-icon').css('color', hex);

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
  Mailpile.tag_update($('#data-tag-tid').val(), 'name', $(this).val(), function(response) {
    Mailpile.tag_update($('#data-tag-tid').val(), 'slug', $('#data-tag-add-slug').val(), function(response) {
      Mailpile.notification(response.status, '{{_("Tag Name & Slug Updated")}}');
    });
  });
});


/* Tag - Update the Slug */
$(document).on('blur', '#data-tag-add-slug', function(e) {
  Mailpile.tag_update($('#data-tag-tid').val(), 'slug', $('#data-tag-add-slug').val(), function(response) {
    Mailpile.notification(response.status, '{{("Tag Name & Slug Updated")}}');
  });
});


/* Tag - Update (multiple attribute events) */
$(document).on('change', '#data-tag-display', function(e) {
  Mailpile.tag_update($('#data-tag-tid').val(), 'display', $(this).val(), function(response) {
    Mailpile.notification(response.status, response.message);
  });  
});


/* Tag - Update parent */
$(document).on('change', '#data-tag-parent', function(e) {
  Mailpile.tag_update($('#data-tag-tid').val(), 'parent', $(this).val(), function(response) {
    Mailpile.notification(response.status, response.message);
  });  
});


$(document).ready(function() {

  // Slugify
  $('#data-tag-add-slug').slugify('#data-tag-add-tag');

});