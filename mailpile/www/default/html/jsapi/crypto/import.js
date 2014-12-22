/* Crypto - Import */


Mailpile.Crypto.Import.Key = function(action, fingerprint) {

  // Show Processing UI feedback
  var importing_template = _.template($('#template-crypto-encryption-key-importing').html());
  var importing_html     = importing_template({ action: action, fingerprint: fingerprint });
  $('#item-encryption-key-' + fingerprint).replaceWith(importing_html);

  // Lookup
  var key_data = _.findWhere(Mailpile.crypto_keylookup, {fingerprints: fingerprint});

  Mailpile.API.crypto_keyimport_post(key_data, function(result) {

    if (result.status === 'success') {

      for (var key in result.result) {
        if (result.result[key].fingerprint === fingerprint) {
          var key_result = result.result[key];

          // FIXME: kludgy
          key_result['avatar'] = '/static/img/avatar-default.png';
          key_result['uid'] = key_result.uids[0];
          key_result['action'] = 'hide-modal';
          key_result['on_keychain'] = true;
        }
      }

      var key_template = _.template($('#template-crypto-encryption-key').html());
      var key_html = key_template(key_result);

      $('#item-encryption-key-' + fingerprint).replaceWith(key_html);
    }
/*
    if (result.status === 'success' && action === 'hide-modal') {
      $('#modal-full').modal('hide');
    }
    else if (result.status === 'success' && action === 'hide-item') {
      // FIXME: kludgy
      $('#item-encryption-key-' + fingerprint).fadeOut();
    }
*/
  });

};


Mailpile.Crypto.Import.Uploader = function() {

  var uploader = new plupload.Uploader({
  	runtimes : 'html5',
  	browse_button : 'upload-key-pick', // you can pass in id...
  	container: 'upload-key-container', // ... or DOM Element itself
    drop_element: 'upload-key-container',
  	url : '/api/0/crypto/gpg/importkey/',
//    multipart : true,
//    multipart_params : {'key_file': 'upload'},
    file_data_name : 'key_data',
  	filters : {
  		max_file_size : '5mb'
  	},
  	init: {
      PostInit: function() {
        $('#upload-key-pick').removeClass('hide');
        $('#upload-key-browswer-unsupported').addClass('hide');
        uploader.refresh();
      },
      FilesAdded: function(up, files) {
  
        // Loop through added files
      	plupload.each(files, function(file) {
  
          // Show Warning for 50 mb or larger
          if (file.size > 52428800) {
            start_upload = false;
            alert(file.name + ' {{_("is")}} ' + plupload.formatSize(file.size) + '. {{_("You can not upload a key larger than 5 Megabytes.")}}');
          } else {

            var importing_template = _.template($('#template-crypto-encryption-key-importing').html());
            var importing_html = importing_template({fingerprint: '!UPLOADING', file: file });            
            $('#upload-key-list').html(importing_html);
            $('#form-upload-key').addClass('hide');

            // Start
            uploader.start();
          }
      	});
      },
      UploadProgress: function(up, file) {
      	$('#' + file.id).find('b').html('<span>' + file.percent + '%</span>');
      },
      FileUploaded: function(up, file, response) {

        console.log(response);

        if (response.status == 200) {

          var response_json = $.parseJSON(response.response);

          // Display UI
          $('#upload-key-list').find('#item-encryption-key-!UPLOADING');


        } else {
          Mailpile.notification({status: 'error', message: '{{_("Encryption key upload failed status")}}: ' + response.status });
        }
      },
      Error: function(up, err) {
        Mailpile.notification({status: 'error', message: '{{_("Could not upload encryption key because")}}: ' + err.message });
        $('#' + err.file.id).find('b').html('Failed ' + err.code);
        uploader.refresh();
      }
    }
  });

  return uploader.init();

};


Mailpile.Crypto.Import.UploaderProcessing = function() {

    

};

Mailpile.Crypto.Import.UploaderComplete = function(key) {

};