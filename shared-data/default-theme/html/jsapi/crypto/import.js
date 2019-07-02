/* Crypto - Import */


Mailpile.Crypto.Import.Key = function(import_data) {
  // Set Null
  if (import_data.file === undefined) import_data.file = false;
  import_data.failed = false;

  // Show Processing UI feedback
  var importing_template = Mailpile.safe_template($('#template-crypto-encryption-key-importing').html());
  var importing_html     = importing_template(import_data);
  $('#item-encryption-key-' + import_data.fingerprint).replaceWith(importing_html);

  // Lookup
  var key_data = _.findWhere(Mailpile.crypto_keylookup,
                             {fingerprints: import_data.fingerprint});

  Mailpile.API.crypto_keyimport_post(key_data, function(result) {
    if (result.status === 'success') {
      var key_result;
      for (var key in result.result) {
        if (result.result[key].fingerprint === import_data.fingerprint) {
          key_result = result.result[key];
          key_result['avatar'] = '{{ U("/static/img/avatar-default.png") }}';
          key_result['uid'] = key_result.uids[0];
          key_result['action'] = 'hide-modal';
          key_result['on_keychain'] = true;
          key_result['score_color'] = Mailpile.UI.Crypto.ScoreColor(key.score_stars);
        }
      }
      console.log(key_result);

      var $key_elem = $('#item-encryption-key-' + import_data.fingerprint);
      var $events = $key_elem.closest('.has-keylookup-events');
      var key_template_html;
      if (key_result) {
        var key_template = Mailpile.safe_template($('#template-crypto-encryption-key').html());
        key_template_html = key_template(key_result);
      }
      else {
        import_data.failed = true;
        key_template_html = importing_template(import_data);
      }
      $key_elem.replaceWith(key_template_html);
      $events.trigger('keylookup:imported');
    }
  });
};


Mailpile.Crypto.Import.Uploader = function() {

  var uploader = new plupload.Uploader({
  	runtimes : 'html5',
  	browse_button : 'upload-key-pick', // you can pass in id...
  	container: 'upload-key-container', // ... or DOM Element itself
    drop_element: 'upload-key-container',
  	url : '{{ config.sys.http_path }}/api/0/crypto/gpg/importkey/',
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
  
        // Hide Message (in case)
        $('#upload-key-container').find('p.message').fadeOut();
        $('#form-upload-key').addClass('hide');

        // Loop through added files
      	plupload.each(files, function(file) {
  
          // Show Warning for 50 mb or larger
          if (file.size > 5242880) {
            start_upload = false;
            alert(file.name + ' {{_("is too large:")|escapejs}} ' + plupload.formatSize(file.size) + '. {{_("You can not upload a key larger than 5 Megabytes.")|escapejs}}');
          } else {

            var importing_template = Mailpile.safe_template($('#template-crypto-encryption-key-importing').html());
            var importing_html = importing_template({fingerprint: 'UPLOADING', file: file });            
            $('#upload-key-list').removeClass('hide').html(importing_html);
            $('#form-upload-key').addClass('hide');

            // Start (with slight delay)
            setTimeout(function() {
              uploader.start();
            }, 500);
          }
      	});
      },
      UploadProgress: function(up, file) {
      	$('#item-encryption-key-UPLOADING').find('em.text-detail').html('Uploading ' + file.name + ' ' + file.percent + '% complete');
      },
      FileUploaded: function(up, file, response) {

        // Delay UI feedback (for local installs)
        setTimeout(function() {
          if (response.status === 200) {
            var response_data = $.parseJSON(response.response);

            // Show UI feedback
            if (response_data.status === 'success') {
              $('#item-encryption-key-UPLOADING').html('Yay. Encrypted Key Successfully Uploaded. Someday this will look nicer :)');
            } else {
              $('#upload-key-container').find('p.message').fadeIn();
              $('#item-encryption-key-UPLOADING').fadeOut().remove();
              $('#form-upload-key').fadeIn().removeClass('hide');
            }
          } else {
            Mailpile.notification({status: 'error', message: '{{_("Could not upload encryption key. Status:")|escapejs}}: ' + response.status });
          }
        }, 1000);
      },
      Error: function(up, err) {
        Mailpile.notification({status: 'error', message: '{{_("Could not upload encryption key because")|escapejs}}: ' + err.message });
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
