/* This is the demo plugin's javascript code!
   The name of the returned class will be `mailpile.plugins.demos`.
 */
return {
    new_tool_click: function() {
        alert('Are you ready to see a whole new world?');
        return false;
    },
    new_tool_setup: function(element) {
        $(element).click(this.new_tool_click);
    },
    new_tool: function() {
        $('#sidebar').fadeOut();
        $('#content').fadeOut();
        $('#header').after('<div id="extreme-mashup" style="position: relative; top: 200px" class="text-center"><h1>ALL YOUR MAILBOX ARE BELONG TO ME</h1><p>This could be an extreme plugin that renders a completely new feature or tool or mashup</p><p><button id="no-extreme">Go Back</button></p></div>');
        $('#no-extreme').on('click', Mailpile.plugins.demos.new_tool_hide);
        return false;
    },
    new_tool_hide: function() {
        $('#extreme-mashup').hide();
        $('#sidebar').fadeIn();
        $('#content').fadeIn();
        return false;
    },
    /* These methods are exposed to the app for various things. */
    earthquake_click: function() {
        alert('Can you feel the rumble?');
        return false;
    },
    earthquake_setup: function(element) {
        /* Setup code for our activity launcher goes here. This function
           gets run after the DOM has created the element, so we can
           'enhance' it. Here we just give it a click handler, but fancier
           plugins could set up event listeners and update the element
           itself based on other app activities. */
        $(element).click(Mailpile.plugins.demos.earthquake_click);
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
    },
    tag_list: function() {
        list_html = '';
        for (var i=0; i < 11; i++) {
          list_html += 'Demo Tag List ' + i + '<hr>';
        }
        $('#tags-list').html(list_html);
        $('#tags-archived-list').hide();
        return false;
    }
};
