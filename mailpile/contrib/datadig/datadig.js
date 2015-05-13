function preview() {
  $('#modal-full .datadig-working').show();
  $('#modal-full .datadig-hints').hide();
  $('#modal-full #datadig-preview').hide();
  $('#modal-full .datadig-preview-area').show();
  Mailpile.API.datadig_get({
    _output: 'as.jhtml',
    _serialized: $('#modal-full .datadig-form').serialize() + '&timeout=5'
  }, function(data) {
    $('#modal-full .datadig-working').hide();
    $('#modal-full #datadig-preview').html(data['result']).fadeIn();
  });
  return false;
}

var column_html = '';
function add_column() {
  $('#modal-full .datadig-data-terms').append($(column_html));
  return false;
}

function set_column_from_hint(i, elem) {
  var cspec = $(this).find('.datadig-cspec').html();
  $('#modal-full .datadig-columns input').last().attr('value', cspec);
}

function show_hints() {
  $('#modal-full .datadig-hints').show();
  $('#modal-full .datadig-preview-area').hide();
}

// Display the datadig widget!
$(document).on('click', '.bulk-action-datadig', function() {
  Mailpile.API.with_template('datadig-modal', function(modal) {
    mf = $('#modal-full').html(modal({}));

    // Extract our data-term template
    column_html = mf.find('.datadig-data-term').html();

    // Add hidden form-fields for all the message metadata-IDs
    $.each(Mailpile.messages_cache, function(key, mid) {
      var input = $('<input type="hidden" name="mid" value="' + mid + '">');
      mf.find('.datadig-form').append(input);
    });

    // Make the hints clickable
    mf.find('.datadig-hints .datadig-hint').click(set_column_from_hint);

    mf.modal(Mailpile.UI.ModalOptions);
  });
});

return {
  'preview': preview,
  'show_hints': show_hints,
  'add_column': add_column
}
