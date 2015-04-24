/* Compose - Attachments */

Mailpile.Composer.Attachments.UploaderImagePreview = function(attachment, file) {

  // Create an instance of the mOxie Image object. This
  // utility object provides several means of reading in
  // and loading image data from various sources.
  // Wiki: https://github.com/moxiecode/moxie/wiki/Image
  var preloader = new mOxie.Image();

  // Define the onload BEFORE you execute the load()
  // command as load() does not execute async.
  preloader.onload = function() {

    // Scale the image (in memory) before rendering it
    preloader.downsize(150, 150);

    // Grab preloaded the Base64 encoded image data
    attachment['attachment_data'] = preloader.getAsDataURL();

    var attachment_image_template = _.template($('#template-composer-attachment-image').html());
    var attachment_image_html = attachment_image_template(attachment);

    // Append template to view
    $('#compose-attachments-files-' + attachment.mid).append(attachment_image_html);
  };

  // Calling the .getSource() returns instance of mOxie.File
  // Wiki: https://github.com/moxiecode/plupload/wiki/File
  preloader.load(file.getSource());
};


Mailpile.Composer.Attachments.ExistingImagePreview = function(attachment, file) {

  // Load static preview
  attachment['attachment_data'] = '/message/download/preview/=' + attachment.mid + '/' + attachment.aid + '/';

  var attachment_image_template = _.template($('#template-composer-attachment-image').html());
  var attachment_image_html = attachment_image_template(attachment);

  // Append template to view
  $('#compose-attachments-files-' + attachment.mid).append(attachment_image_html);
};


Mailpile.Composer.Attachments.UpdatePreviews = function(attachments, mid, file) {

  // Loop through attachments
  _.each(attachments, function(attachment, key) {

    if (!$('#compose-attachment-' + mid + '-' + attachment.aid).length) {

      attachment['previewable'] = _.indexOf(['image/bmp', 
                                      'image/gif',
                                      'image/jpg',
                                      'image/jpeg',
                                      'image/pjpeg',
                                      'image/x-png',
                                      'image/png',
                                      'application/vnd.google-apps.photo'], attachment.mimetype);

      if (file && file.name === attachment.filename) {
        attachment['is_file'] = true;
      } else {
        attachment['is_file'] = false;
      }

      // More UI friendly values
      var file_parts = attachment.filename.split('.');
      var file_parts_length = file_parts.length
    
      if (file_parts.length > 2 || attachment.filename.length > 20) {
        attachment['name_fixed'] = attachment.filename.substring(0, 16);
      } else {
        attachment['name_fixed'] = file_parts[0];
      }

      attachment['mid'] = mid;
      attachment['size'] = plupload.formatSize(attachment.length);
      attachment['extension'] = file_parts[file_parts.length - 1];

      // Determine Preview Type (live image, req image, graphic)
      if (attachment.previewable > -1 && attachment.is_file) {
        Mailpile.Composer.Attachments.UploaderImagePreview(attachment, file);
      }
      else if (attachment.previewable > -1 && !attachment.is_file) {
        Mailpile.Composer.Attachments.ExistingImagePreview(attachment);
      }
      else {
        var attachment_template = _.template($('#template-composer-attachment').html());
        var attachment_html = attachment_template(attachment);
      	$('#compose-attachments-files-' + mid).append(attachment_html);
      }
    } else {
      console.log('attachment exists ' + attachment.aid);
    }
  });
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
  
        // Loop through added files
      	plupload.each(files, function(file) {
  
          // Show Warning for 50 mb or larger
          if (file.size > 52428800) {
            start_upload = false;
            alert(file.name + ' {{_("is")}} ' + plupload.formatSize(file.size) + '. {{_("Some people cannot receive attachments larger than 50 Megabytes.")}}');
          } else {

            // Start
            uploader.start();
          }
      	});
      },
      UploadProgress: function(up, file) {
      	$('#' + file.id).find('b').html('<span>' + file.percent + '%</span>');
      },
      FileUploaded: function(up, file, response) {

        if (response.status == 200) {

          var response_json = $.parseJSON(response.response);
          var new_mid = response_json.result.message_ids[0];

          //console.log(file);
          Mailpile.Composer.Attachments.UpdatePreviews(response_json.result.data.messages[new_mid].attachments, settings.mid, file);

        } else {
          Mailpile.notification({status: 'error', message: '{{_("Attachment upload failed status")}}: ' + response.status });
        }
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
  Mailpile.API.message_unattach_post({ mid: mid, att: aid }, function(result) {
    if (result.status == 'success') {
      $('#compose-attachment-' + mid + '-' + aid).fadeOut(function() {
        $(this).remove();
        Mailpile.Composer.Attachments.UpdatePreviews(result.result.data.messages[mid].attachments, mid, false);
      });
    } else {
      Mailpile.notification(result);
    }
  });
};

