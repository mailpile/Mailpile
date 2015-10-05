var disabled = false;

function preview() {
  if (disabled) return false;
  $('#modal-full .datadig-hints').hide();
  $('#modal-full #datadig-preview').hide();
  $('#modal-full .datadig-working').show();
  $('#modal-full .datadig-preview-area').show();
  Mailpile.API.datadig_get({
    _output: 'as.jhtml',
    _serialized: $('#modal-full .datadig-form').serialize() + '&timeout=3'
  }, function(data) {
    $('#modal-full .datadig-working').hide();
    $('#modal-full #datadig-preview').html(data['result']).fadeIn();
  });
  return false;
}

var column_html = '';
function add_column() {
  if (disabled) return false;
  $('#modal-full .datadig-data-terms').append($(column_html));
  $('#modal-full .datadig-data-terms input').last().focus();
  return false;
}

function set_column_from_hint(i, elem) {
  if (disabled) return false;
  var cspec = $(this).find('.datadig-cspec').html();
  $('#modal-full .datadig-columns input').last().attr('value', cspec);
}

function show_hints() {
  if (disabled) return false;
  $('#modal-full .datadig-hints').show();
  $('#modal-full .datadig-preview-area').hide();
}

function download() {
  if (disabled) return false;
  disabled = true;

  // Add hidden form-field for tracking progress
  var track_id = '@' + (new Date()).getTime();
  var input = $('<input class="datadig-track-id" type="hidden" name="track-id" value="' + track_id + '">');
  mf.find('.datadig-track-id').remove();
  mf.find('.datadig-form').append(input);

  // Change state of UI...
  $('#modal-full .datadig-hints').hide();
  $('#modal-full #datadig-preview').hide();
  $('#modal-full .datadig-working').show();
  $('#modal-full .datadig-downloading').show();
  $('#modal-full .datadig-preview-area').show();
  $('#modal-full .modal-footer').css('opacity', 0.5);

  // This changes the state of the modal to show the progress of our
  // data extraction, by temporarily subscribing to the EventLog.
  var ev_source = '.*datadig.dataDigCommand';
  var watch_id = EventLog.subscribe(ev_source, function(ev) {
    if (ev.private_data['track-id'] == track_id) {
      if (ev.flags == "c") {
        // Completed! Revert UI back to normal, unsubscribe from events
        disabled = false;
        $('#modal-full .datadig-hints').show();
        $('#modal-full .datadig-working').hide();
        $('#modal-full .datadig-downloading').hide();
        $('#modal-full .datadig-preview-area').hide();
        $('#modal-full .modal-footer').css('opacity', 1.0);
        EventLog.unsubscribe(ev_source, watch_id);
      }
      else {
        // Otherwise, report progress!
        $('#modal-full #datadig-downloading-progress').html(
          ev.private_data.progress + ' / ' + ev.private_data.total
        );
      }
    }
  });
}

// Display the datadig widget!
$(document).on('click', '.bulk-action-datadig', function() {
  var $context = $(this);
  Mailpile.API.with_template('datadig-modal', function(modal) {
    mf = $('#modal-full').html(modal({
      context: $('#search-query').data('context')
    }));

    // Extract our data-term template
    column_html = mf.find('.datadig-data-term').html();

    // Add hidden form-fields for all the message metadata-IDs
    $.each(Mailpile.UI.Selection.selected($context), function(key, mid) {
      var input = $('<input type="hidden" name="mid" value="' + mid + '">');
      mf.find('.datadig-form').append(input);
    });

    // Make the hints clickable
    mf.find('.datadig-hints .datadig-hint').click(set_column_from_hint);

    disabled = false;
    mf.modal(Mailpile.UI.ModalOptions);
    mf.find('.datadig-data-terms input').last().focus();
  });
});

// Expose these methods as Mailpile.plugins.datadig.*
return {
  'preview': preview,
  'show_hints': show_hints,
  'add_column': add_column,
  'download': download
}
