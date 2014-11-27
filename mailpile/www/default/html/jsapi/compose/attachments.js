/* Compose - Attachments */

Mailpile.Composer.Attachments.UploaderImagePreview = function(file) {

  // Create an instance of the mOxie Image object. This
  // utility object provides several means of reading in
  // and loading image data from various sources.
  // Wiki: https://github.com/moxiecode/moxie/wiki/Image
  var preloader = new mOxie.Image();

  // Define the onload BEFORE you execute the load()
  // command as load() does not execute async.
  preloader.onload = function() {

    // Scale the image (in memory) before rendering it
    preloader.downsize(150, 125);

    // Grab preloaded the Base64 encoded image data
    file['attachment_data'] = preloader.getAsDataURL();

    var attachment_image_template = _.template($('#template-composer-attachment-image').html());
    var attachment_image_html = attachment_image_template(file);

    // Append template to view
    $('#compose-attachments-files-' + file.mid).append(attachment_image_html);
  };

  // Calling the .getSource() returns instance of mOxie.File
  // Wiki: https://github.com/moxiecode/plupload/wiki/File
  preloader.load(file.getSource());
};


Mailpile.Composer.Attachments.Uploader = function(settings) {

  var uploader = new plupload.Uploader({
  	runtimes : 'html5',
  	browse_button : settings.browse_button, // you can pass in id...
  	container: settings.container, // ... or DOM Element itself
    drop_element: settings.container,
  	url : '/api/0/message/attach/',
    multipart : true,
    multipart_params : {'mid': settings.mid},
    file_data_name : 'file-data',
  	filters : {
  		max_file_size : '50mb'
  	},
    resize: {
      width: '3600',
      height: '3600',
      crop: true,
      quaility: 100
    },
    views: {
      list: true,
      thumbs: true,
      active: 'thumbs'
    },
  	init: {
      PostInit: function() {
        $('#compose-attachments-' + settings.mid).find('.compose-attachment-pick').removeClass('hide');
        $('#compose-attachments-' + settings.mid).find('.attachment-browswer-unsupported').addClass('hide');
        uploader.refresh();
      },
      FilesAdded: function(up, files) {
        var start_upload = true;
  
        // Upload files
      	plupload.each(files, function(file) {
  
          // Values for templates
          file['mid'] = settings.mid;
          file['aid'] = file.id;

          // Show Warning for 50 mb or larger
          if (file.size > 52428800) {
            start_upload = false;
            alert(file.name + ' {{_("is")}} ' + plupload.formatSize(file.size) + '. {{_("Some people cannot receive attachments larger than 50 Megabytes.")}}');
          } else {
           // Show image preview
            if (_.indexOf(['image/bmp', 'image/gif', 'image/jpeg', 'image/pjpeg', 'image/svg+xml', 'image/x-png', 'image/png', 'application/vnd.google-apps.photo'], file.type) > -1) {
              Mailpile.Composer.Attachments.UploaderImagePreview(file);
            } else {

              // More UI friendly values
              var file_parts = file.name.split('.');
              var file_parts_length = file_parts.length

              if (file_parts.length > 2 || file.name.length > 20) {
                file['name_fixed'] = file.name.substring(0, 16);
              } else {
                file['name_fixed'] = file_parts[0];
              }

              file['size'] = plupload.formatSize(file.size);
              file['extension'] = file_parts[file_parts.length - 1];

              // Add to UI
              var attachment_template = _.template($('#template-composer-attachment').html());
              var attachment_html = attachment_template(file);
          		$('#compose-attachments-files-' + settings.mid).append(attachment_html);
            }
          }
      	});

        // Start
        if (start_upload) {
          uploader.start();
        }
      },
      UploadProgress: function(up, file) {
      	$('#' + file.id).find('b').html('<span>' + file.percent + '%</span>');
      },
      Error: function(up, err) {
        Mailpile.notification({status: 'error', message: '{{_("Could not upload attachment because")}}: ' + err.message });
        $('#' + err.file.id).find('b').html('Failed ' + err.code);
        uploader.refresh();
      }
    }
  });

  return uploader.init();
};


Mailpile.Composer.Attachments.Remove = function(mid, aid) {

  // Fix me, add UI of deleting to current attachment

  Mailpile.API.message_unattach_post({ mid: mid, att: aid }, function(result) {
    if (result.status == 'success') {
      $('#compose-attachment-' + mid + '-' + aid).remove();
    } else {
      Mailpile.notification(result);
    }
  });
};

