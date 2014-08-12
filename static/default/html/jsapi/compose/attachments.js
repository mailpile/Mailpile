/* Compose - Attachments uploader */
var uploader = function(settings) {

  var dom = {
    uploader: $('#compose-attachments-' + settings.mid),
    uploads: $('#compose-attachments-files-' + settings.mid)
  };

  var upload_image_preview = function(file) {

    var item = $("<li></li>").prependTo(dom.uploads);
    var image = $(new Image()).appendTo(item);

    // Create an instance of the mOxie Image object. This
    // utility object provides several means of reading in
    // and loading image data from various sources.
    // Wiki: https://github.com/moxiecode/moxie/wiki/Image
    var preloader = new mOxie.Image();

    // Define the onload BEFORE you execute the load()
    // command as load() does not execute async.
    preloader.onload = function() {

        // This will scale the image (in memory) before it
        // tries to render it. This just reduces the amount
        // of Base64 data that needs to be rendered.
        preloader.downsize(100, 100);

        // Now that the image is preloaded, grab the Base64
        // encoded data URL. This will show the image
        // without making an Network request using the
        // client-side file binary.
        image.prop("src", preloader.getAsDataURL());
    };

    // Calling the .getSource() on the file will return an
    // instance of mOxie.File, which is a unified file
    // wrapper that can be used across the various runtime
    // Wiki: https://github.com/moxiecode/plupload/wiki/File
    preloader.load(file.getSource());
  };

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
		max_file_size : '50mb',
		mime_types: [
			{title : "Audio files", extensions : "mp3,aac,flac,wav,ogg,aiff,midi"},
			{title : "Document files", extensions : "pdf,doc,docx,xls"},
			{title : "Image files", extensions : "jpg,gif,png,svg"},
			{title : "Image files", extensions : "mp2,mp4,mov,avi,mkv"},
			{title : "Zip files", extensions : "zip,rar"},
			{title : "Crypto files", extensions : "asc,pub,key"}
		]
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

    	plupload.each(files, function(file) {

        // Show Preview while uploading
        upload_image_preview(file);

        // Add to attachments
        var attachment_html = '<li id="' + file.id + '">' + file.name + ' (' + plupload.formatSize(file.size) + ') <b></b></li>';
    		$('#compose-attachments-files').append(attachment_html);

        console.log(file);

        // Show Warning for 10mb or larger
        if (file.size > 10485760) {
          start_upload = false;
          alert(file.name + ' is ' + plupload.formatSize(file.size) + '. Some people cannot receive attachments that are 10 mb or larger');
        }
    	});

      if (start_upload) {
        uploader.start();
      }
    },
    UploadProgress: function(up, file) {
    	$('#' + file.id).find('b').html('<span>' + file.percent + '%</span>');
    },
    Error: function(up, err) {
      console.log("Error #" + err.code + ": " + err.message);
      $('#' + err.file.id).find('b').html('Failed');
      uploader.refresh();
    }
  }
  });

  return uploader.init();
};