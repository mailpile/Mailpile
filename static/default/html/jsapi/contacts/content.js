MailPile.prototype.contact_add = function(form_name, complete) {
  $.ajax({
    url      : '/api/0/contacts/add/',
    type     : 'POST',
    data     : $(form_name).serialize(),
    dataType : 'json',
    success  : function(response) {
      console.log(response);
      if (response.status === 'success') {
        complete(response.result);
      }
    }
  });
};


/* Show Contact Add Form */
$(document).on('click', '.btn-activity-contact_add', function(e) {

  e.preventDefault();

  $('.sub-navigation ul li').removeClass('navigation-on');
  $(this).addClass('navigation-on');

  var modal_data = { name: '', address: '', extras: '' };
  var modal_html = $("#modal-contact-add").html();
  $('#modal-full').html(_.template(modal_html, modal_data));
  $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
});


/* Contact - Add */
$(document).on('submit', '#form-contact-add', function(e) {
  e.preventDefault();
  mailpile.contact_add('#form-contact-add', function() {
    alert('Woot, contact added');
  });
});


$(document).on('blur', '.contact-add-name, .contact-add-email', function(e) {
  if ($(this).val() !== '') {
    var search_query  = $('.contact-add-name').val() + ' ' + $('.contact-add-email').val();
    var search_button = _.template($('#template-search-keyserver').html(), { query: search_query });
    $('#contact-search-keyserver-input').html(search_button);
  }
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
        $('#contact-search-keyserver-result').html('Oopsie daisy something is wrotten in Denmark :(');
      }
    }
  });  
});


/* Contacts - View Page */
function extractEmailFromLocation() {
  var pathname = decodeURIComponent(location.pathname);
  var parts = pathname.split('/').filter(function(el) {return el.length > 0})
  return parts[parts.length - 1]
}

$('.contact-key-use').on('change', function(e) {
  alert('This will update a KEYS USE state');
});


$('#crypto-policy').on('change', function(e) {
    var policy = e.val
    var email = extractEmailFromLocation()
    var data = { email: email, policy: policy }

    $.ajax({
        url : '/api/0/crypto_policy/set/',
        type : 'POST',
        data : data,
        dataType : 'json'
    })
  console.log('Changed')
})


$('.show-key-details').on('click', function(e) {
  e.preventDefault();
  $(this).hide();
  var keyid = $(this).data('keyid');
  $('#contact-key-details-' + keyid).fadeIn();
});


$(document).ready(function() {

  // Hide Key Details
  $('.contact-key-details').hide();

});