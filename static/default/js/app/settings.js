/* Profile Add */
$(document).on('submit', '#form-profile-add', function(e) {

  e.preventDefault();
  var smtp_data = $('#profile-add-username').val() + ':' + $('#profile-add-password').val() + '@' + $('#profile-add-server').val() + ':' + $('#profile-add-port').val();
    
  if (smtp_data !== ':@:25') {
    smtp_data = 'smtp://' + smtp_data;
  }
  else {
    smtp_data = 'default';
  }

  var profile_data = {
    profiles: {
      name : $('#profile-add-name').val(),
      email: $('#profile-add-email').val(),
      route: smtp_data
    }
  };

	$.ajax({
		url			 : '/api/0/settings/add/',
		type		 : 'POST',
		data     : profile_data,
		dataType : 'json',
	  success  : function(response) {

      statusMessage(response.status, response.message);

      if (response.status == 'success') {
        console.log(response);
        //window.location.href = ''
      }
	  }
	});

});