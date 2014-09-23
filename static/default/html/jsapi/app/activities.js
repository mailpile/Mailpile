/* Activities */
Mailpile.activities.compose = function(address) {
  var compose_data = {};
  if (address) {
    compose_data = {to: address};
  }
	Mailpile.API.message_compose_post(compose_data, function(response) {
    if (response.status === 'success') {
      window.location.href = Mailpile.urls.message_draft + response.result.created[0] + '/';
    } else {
      Mailpile.notification(response);
    }
  });
};