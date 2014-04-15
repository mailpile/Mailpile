/* This is the demo plugin's javascript code!
   The name of the returned class will be `mailpile.plugins.demos`.
 */
return {
    /* These methods are exposed to the app for various things. */
    activity_click: function() {
        alert('You clicked the demo activity!');
        return false;
    },
    activity_setup: function(element) {
        /* Setup code for our activity launcher goes here. This function
           gets run after the DOM has created the element, so we can
           'enhance' it. Here we just give it a click handler, but fancier
           plugins could set up event listeners and update the element
           itself based on other app activities. */
        $(element).click(new_mailpile.plugins.demos.activity_click);
    }
};
