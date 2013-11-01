// STATICALLY DECLARED PLUGINS - TOTAL HACK RIGHT NOW SO I CAN JUST WORK ON SPECING THINGS OUT
// I THINK THIS SHOULD BE INJECTED VIA PYTHON or FROM AN API ENDPOINT
var plugins_hack = ["force-grapher","maildeck"];


/* Load Plugins - THIS SHOULD ALSO JUST BE INJECTED BY PYTHON METHINKS */
$.each(plugins_hack, function(key, plugin){

  var params = '';

  $.getJSON('/static/plugins/' + plugin + '/config.json', params, function(result) {

    // Add To Config
    mailpile.plugins.push(result);
    
    var view_index = _.indexOf(result.views, mailpile.instance.command);

    if (view_index > -1) {
      $.ajax({
		    url			 : '/static/plugins/' + plugin + '/' + result.views[view_index] + '.html',
		    type		 : 'GET',
		    dataType : 'html',
	      success  : function(response) {
          $('body').append(response);
	      }
	    });   
    }
    
  });

});