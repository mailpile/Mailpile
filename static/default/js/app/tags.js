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


/* Show Tag Add Form */
$(document).on('click', '#button-tag-add', function(e) {

  e.preventDefault();
  $('#tags-list').hide();
  $('#tags-archived-list').hide();
  $('#tag-add').show();

  $('.sub-navigation ul li').removeClass('navigation-on');
  $(this).parent().addClass('navigation-on');
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
        console.log(response);
      }
    }
  });
});