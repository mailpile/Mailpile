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


/* Show Tag Add Form */
$(document).on('click', '#button-tag-add', function(e) {

  e.preventDefault();
  $('#tags-list').hide();
  $('#tags-archived-list').hide();
  $('#tag-add').show();

  $('.sub-navigation ul li').removeClass('navigation-on');
  $(this).parent().addClass('navigation-on');
  
  $('#data-tag-add-slug').slugify('#data-tag-add-tag');
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
        mailpile.notification(response.status, response.message);
      }
    });
  }

});