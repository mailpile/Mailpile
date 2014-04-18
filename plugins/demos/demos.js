/* This is the demo plugin's javascript code!
   The name of the returned class will be `mailpile.plugins.demos`.
 */
return {
    /* These methods are exposed to the app for various things. */
    activity_click: function() {
        alert('Are you ready to see a whole new world?');
        return false;
    },
    activity_setup: function(element) {
        /* Setup code for our activity launcher goes here. This function
           gets run after the DOM has created the element, so we can
           'enhance' it. Here we just give it a click handler, but fancier
           plugins could set up event listeners and update the element
           itself based on other app activities. */
        $(element).click(new_mailpile.plugins.demos.activity_click);
    },
    new_tool: function() {
        $('#sidebar').fadeOut();
        $('#content').fadeOut();
        $('#header').after('<div style="position: relative; top: 200px" class="text-center"><h1>ALL YOUR MAILBOX ARE BELONG TO ME</h1><p>This could be an extreme plugin that renders a completely new feature or tool or mashup</p></div>');
    },
    tag_list: function() {
        list_html = '';
        for (var i=0; i < 10; i++) { 
          list_html += 'Demo Tag List ' + i + '<hr>';
        }
    
        $('#tags-list').html(list_html);
        return false;      
    },
    earthquake: function(element) {
      $(".boxy").animate({"margin-left": -5}, 40)
                .animate({"margin-left": 5}, 40)
                .animate({"margin-left": -5}, 40)
                .animate({"margin-left": 5}, 40)
                .animate({"margin-left": -5}, 40)
                .animate({"margin-left": 5}, 40)
                .animate({"margin-left": -5}, 40)
                .animate({"margin-left": 5}, 40)
                .animate({"margin-left": -5}, 40)
                .animate({"margin-left": 5}, 40)
                .animate({"margin-left": -5}, 40)
                .animate({"margin-left": 5}, 40);
    }
};
