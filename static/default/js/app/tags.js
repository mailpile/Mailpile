MailPile.prototype.tag = function(msgids, tags) {};

MailPile.prototype.tag_list = function(complete) {
  $.ajax({
    url      : mailpile.api.tag_list,
    type     : 'GET',
    dataType : 'json',
    success  : function(response) {
      if (response.status === 'success') {
        complete(response.result);
      }
    }
  });
};

/* Pile - Tag Add */
MailPile.prototype.tag_add = function(tag_add, mids, complete) {
  $.ajax({
	  url			 : mailpile.api.tag,
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
        mailpile.notification(response.status, response.message);
      }
    }
  });
};


MailPile.prototype.tag_add_delete = function(tag_add, tag_del, mids, complete) {
  $.ajax({
	  url			 : mailpile.api.tag,
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
        mailpile.notification(response.status, response.message);
      }
    }
  });
};

MailPile.prototype.tag_update = function(tid, setting, value, complete) {

  // Prep Update Value
  var key = 'tags.' + tid + '.' + setting;
  var setting = {};
  setting[key] = value;

  $.ajax({
	  url			 : mailpile.api.tag_update,
	  type		 : 'POST',
	  data     : setting,
	  dataType : 'json',
    success  : function(response) {
      if (response.status == 'success') {
        complete(response.result);
      } else {
        mailpile.notification(response.status, response.message);
      }
    }
  });
};

MailPile.prototype.render_modal_tags = function() {
  if (mailpile.messages_cache.length) {

    // Open Modal with selection options
    mailpile.tag_list(function(result) {
  
      var tags_html = '';
      var archive_html = '';
  
      $.each(result.tags, function(key, value) {
        if (value.display === 'tag') {
          tags_html += '<li class="checkbox-item-picker" data-tid="' + value.tid + '" data-slug="' + value.slug + '"><input type="checkbox"> ' + value.name + '</li>';
        }
        else if (value.display === 'archive') {
          archive_html += '<li class="checkbox-item-picker"><input type="checkbox"> ' + value.name + '</li>';
        }
      });
  
      var modal_html = $("#modal-tag-picker").html();
      $('#modal-full').html(_.template(modal_html, { tags: tags_html, archive: archive_html }));
      $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
    });
 
  } else {
    // FIXME: Needs more internationalization support
    alert('No Messages Selected');
  }
};


$(document).on('click', '#button-tag-change-icon', function() {

  var icons = [
    "icon-comment",
    "icon-forum",
    "icon-donate",
    "icon-news",
    "icon-photos",
    "icon-image",
    "icon-video",
    "icon-themes",
    "icon-links",
    "icon-document",
    "icon-text",
    "icon-travel",
    "icon-money",
    "icon-receipts",
    "icon-trophy",
    "icon-calendar",
    "icon-spreadsheet",
    "icon-attachment",
    "icon-user",
    "icon-groups",
    "icon-graph",
    "icon-list",
    "icon-checkmark",
    "icon-alerts",
    "icon-zip",
    "icon-work",
    "icon-star",
    "icon-rss",
    "icon-robot",
    "icon-code",
    "icon-privacy",
    "icon-music",
    "icon-lock-closed",
    "icon-key",
    "icon-trash",
    "icon-home",
    "icon-new"
  ];

  var icons_html = '';

  $.each(icons, function(key, icon) {
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

  mailpile.tag_update(tid, 'icon', icon, function() {

    // Update Sidebar
    $('.sidebar-icon').removeClass(old).addClass(icon);

    // Update Tag Editor
    $('#data-tag-icon').val(icon);
    $('#tag-editor-icon').removeClass().addClass(icon);
    $('#modal-full').modal('hide');
  });
});


$(document).on('click', '#button-tag-change-label-color', function(e) {
  
  
});


/* API - Tag Add */
$(document).on('submit', '#form-tag-add', function(e) {

  e.preventDefault();
  var tag_data = $('#form-tag-add').serialize();

  $.ajax({
    url: mailpile.api.tag_add,
    type: 'POST',
    data: tag_data,
    dataType : 'json',
    success: function(response) {

      mailpile.notification(response.status, response.message);

      if (response.status === 'success') {
      
        // Reset form fields
        $('#data-tag-add-tag').val('');
        $('#data-tag-add-slug').val('');
        $('#data-tag-add-display option[value="tag"]').prop("selected", true);
        $('#data-tag-add-parrent option[value=""]').prop("selected", true);
        $('#data-tag-add-template option[value="default"]').prop("selected", true);
        $('#data-tag-add-search-terms').val('');
        
        // Reset Slugify
        $('#data-tag-add-slug').slugify('#data-tag-add-tag');
      }
    }
  });
});


/* Tag - Delete Tag */
$(document).on('click', '#button-tag-delete', function(e) {
  if (confirm('Sure you want to delete this tag?') === true) { 
    $.ajax({
      url: '/api/0/tag/delete/',
      type: 'POST',
      data: {tag: $('#data-tag-add-slug').val() },
      dataType : 'json',
      success: function(response) {
        mailpile.notification(response.status, response.message, 'redirect', '/tag/list/');
      }
    });
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


/* Tag - Update */
$(document).on('blur', '#data-tag-add-tag', function(e) {

  alert('Saving: ' + $(this).val())  

});




