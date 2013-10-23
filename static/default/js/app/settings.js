/* Profile Add */
$(document).on('submit', '#form-profile-add', function(e) {

  console.log('here');

  e.preventDefault();

  var profile_data = {
    profiles: {
      name : $('#profile-add-name').val(),
      email: $('#profile-add-email').val(),
      route: 'smtp://' + $('#profile-add-username').val() + ':' + $('#profile-add-password').val() + '@' + $('#profile-add-server').val() + ':' + $('#profile-add-port').val()
    }
  };

  console.log(JSON.stringfy(profile_data));
/*
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
  */
});