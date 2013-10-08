# Front-End Development

Here are some notes about the current build process to work on the front-end code of Mailpile. This is a  rough draft of front-end documentation but it will be more fleshed out soon.

## Themes

Currently, there is only one known theme for Mailpile, it is called "Default" and is located in **/static/default** folder of the Mailpile codebase.

## JavaScripts

To run Mailpile with JavaScript, which is required for write actions (compose, adding tags, contacts, etc...) the following two JS files must be included in your theme.

mailpile.js
mailpile-libraries.js

These files get minified down into the following:

mailpile-min.js
mailpile-libraries-min.js

There are numerous ways to minify JS files. Currently I am developing using a Mac app called CodeKit which handles both JS and CSS using LESS, a popular preprocessor that you can learn more about at http://lesscss.org 

The current file dependencies that get included in **mailpile-libraries.js** is the following:

* jquery.ui.core.js
* jquery.ui.widget.js
* jquery.ui.mouse.js
* jquery.ui.position.js
* jquery.ui.sortable.js
* jquery.ui.droppable.js
* jquery.ui.draggable.js
* select2.min.js
* mousetrap.min.js

I don't expect anyone else to use CodeKit as it is a MacApp that costs money. I plan to add config suport for Grunt and other free/open types of precompilers for both JS and CSS. Until I get around to it, please submit patches and front-end code in separate files that you manually include that I can compile into the main files.


## CSS

The main CSS file that is used is called **default.css** which SHOULD match the name of the theme it is for. Additional CSS files that are only needed for specific parts of the app or for a plugin can be included separately. 

Another thing of note is the CSS is compiled using LESS 


## Font Icons

This is the most fancy modern approach to icons- it works in all the modern browsers. To use this type of icon copy the contents of Font-Icons/fonts folder into your public assets folder and then copy the contents of style.css into your existing CSS files. Then you easily display an icon where ever you want with a simple class like this:

<span class="icon-user"></span>
The full list of these class names is in Font-Icons/index.html. In this file you will see there is another method of displaying these icons, but I've always preffered the .class method.

These were created with a free tool called Ico Moon http://icomoon.io in order to add or update to this icon font import the file Font-Icons.json once inside the app update additional .svg files saved at 48x48px then export. The interface is quite intuitive and easy to use.