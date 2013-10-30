/* Profile Add */
$(document).on('submit', '#form-profile-add', function(e) {

  e.preventDefault();

  var profile_data = {
      name : $('#profile-add-name').val(),
      email: $('#profile-add-email').val()
  };

  var smtp_route = $('#profile-add-username').val() + ':' + $('#profile-add-password').val() + '@' + $('#profile-add-server').val() + ':' + $('#profile-add-port').val();

  if (smtp_route !== ':@:25') {
    profile_data.route = 'smtp://' + smtp_route;
  }

	$.ajax({
		url			 : mailpile.api.settings_add,
		type		 : 'POST',
		data     : {profiles: JSON.stringify(profile_data)},
		dataType : 'json',
	  success  : function(response) {

      statusMessage(response.status, response.message);

      if (response.status == 'success') {
        console.log(response);
      }
	  }
	});

});