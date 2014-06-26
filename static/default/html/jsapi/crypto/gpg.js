/* Crypto - Receive key from keyserver */
$(document).on('click', '.contact-add-search-item', function() {

  var key_data = { keyid: $(this).data('keyid') };

  $('#contact-search-keyserver-input').html('');
  $('#contact-search-keyserver-result').html('');

  $.ajax({
    url      : '/api/0/crypto/gpg/receivekey/',
    type     : 'POST',
    data     : key_data,
    dataType : 'json',
    success  : function(response) {
      $('#contact-add-key').html('<span class="icon-key"></span> PGP Key: ' + key_data.keyid);
      if (response.status === 'success') {
        $('#contact-search-keyserver-result').html('w00t, something here will happen with this key: ' + response.result);
      } else {
        $('#contact-search-keyserver-result').html('Oopsie daisy something is rotten in Denmark :(');
      }
    }
  });  
});


$(document).on('click', '#button-contact-search-keyserver', function(e) {
  e.preventDefault();

  // Update Querying UI Feedback
  $(this).hide();
  $('#contact-search-keyserver-query').hide();
  $('#contact-search-keyserver-input label').html($(this).data('searching'));
  $('#contact-search-keyserver-result').html('<img src="/static/css/select2-spinner.gif">');

  var search_complete = $(this).data('complete');
  var search_query = $(this).data('query');

  $.ajax({
    url      : '/api/0/crypto/gpg/searchkey/?q=' + search_query,
    type     : 'GET',
    dataType : 'json',
    success  : function(response) {
      if (response.status === 'success' && _.isEmpty(response.result) === false) {

        // Update Title
        $('#contact-search-keyserver-input label').html(_.size(response.result) + ' ' + search_complete + ' ' + search_query);

        // Build Results
        var items = '';
        var item_html = $('#template-search-keyserver-item').html();

        $.each(response.result, function(keyid, object) {
          $.each(object.uids, function(key, value) {
            items += _.template(item_html, { 
              keyid: keyid,
              keysize: object.keysize,
              keytype: object.keytype,
              created: object.created,
              name: value.name, 
              email: value.email
            });
          });
        });

        // Display Results
        $('#contact-search-keyserver-result').html('<ul>' + items + '</ul>');
      }
      else if (response.status === 'success' && _.isEmpty(response.result) === true) {
        $('#contact-search-keyserver-input label').html('<p>No keys found</p>');
      }
    }
  });
});