/* Composer - Body */

// This is rough, and isn't being fully used yet
Mailpile.Composer.Model = {
  to:  [], // Something like { fn: '', address: '', secure: false}
  cc:  [],
  bcc: [],
  subject: '',
  body: '',
  quoted_reply: '',
  attachements: [],
  datetime: 0,
  crypto: {
    encrypt: false,
    sign: false,
    type: 'openpgp',
    email_key: false,
  }
};


Mailpile.Composer.Body.Setup = function(mid) {

  // Add Autosize
  $('#compose-text-' + mid).autosize();

  // Is Ephemeral (means .compose-text has quoted_reply)
  if (/\breply-all\b/g.test(mid)) {

    console.log('Is Ephemeral');

    // Add Quoted to Model
    Mailpile.Composer.Drafts[mid].quoted_reply = $('#compose-text-' + mid).val();

    // If Quoted Reply disabled, remove from field
    if ($('#compose-quoted-reply-' + mid).parent().data('quoted_reply') === 'disabled') {
      $('#compose-text-' + mid).val('').trigger('autosize.resize');
    }
    // Not disabled, add to model
    else {
      Mailpile.Composer.Drafts[mid].body = $('#compose-text-' + mid).val();
    }
  }
  // Is Draft add to model
  else {

    console.log('Is Not Ephemeral');

    Mailpile.Composer.Drafts[mid].body = $('#compose-text-' + mid).val();
  }
};


Mailpile.Composer.Body.QuotedReply = function(mid, state) {

  $checkbox = $('#compose-quoted-reply-' + mid);

  if ($checkbox.is(':checked')) {
    $checkbox.val('yes');
  }
  else {
    $checkbox.val('no');

    // Check Quoted Setting State
    if (state === 'unset' && Mailpile.Composer.Drafts[mid].quoted_reply) {
      Mailpile.Composer.Body.QuotedReplySetup();
      $('#compose-text-' + mid).val('').trigger('autosize.resize');
    } 
    // Empty body & .compose-text as it's just a quoted reply
    else if (Mailpile.Composer.Drafts[mid].body === Mailpile.Composer.Drafts[mid].quoted_reply) {
      Mailpile.Composer.Drafts[mid].body = '';
      $('#compose-text-' + mid).val('').trigger('autosize.resize');
    }
    // Replace composer with quoted reply
    else if (Mailpile.Composer.Drafts[mid].quoted_reply) {
      Mailpile.Composer.Drafts[mid].body = Mailpile.Composer.Drafts[mid].quoted_reply;
      $('#compose-text-' + mid).val(Mailpile.Composer.Drafts[mid].quoted_reply).trigger('autosize.resize');
    }
  }
};


Mailpile.Composer.Body.QuotedReplySetup = function() {
 var modal_template = _.template($('#modal-compose-quoted-reply').html());
 $('#modal-full').html(modal_template());
 $('#modal-full').modal(Mailpile.UI.ModalOptions);
};