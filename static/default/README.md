Rebar
=====

Rebar helps make developing the front-end CSS of your application easy. Born out of frustration with existing offerings- frameworks like Bootstrap & Foundation are too heavy & opinated when it comes to design. Ever tried making a site with Bootstrap that doesn't look like a site made with Bootstrap? While possible, doing so requires you to dive in an learn the Bootstrap deeply. Meanwhile, bolierplates like HTML5 or GoldenGrid, are much too small of a building block to build a real web application I often found myself doing uneccesary repetitive scaffolding & mixing of libraries and helpers just to get going.

If you are like me and found neither extreme a good fit- Rebar might be right for you. Also, many of the aspects of Rebar are what is considered modern front-end development- webfonts, CSS preprocessors, SVG icons. As we have included these things we have also tried to explain them to those unfamiliar.

Think of Rebar as a toolbox + some blueprints to help you get building beautiful modern responsive web applications quickly. Additionally, Rebar aims to provide you with an dependency architecture that should meet most of your needs without getting in your way no mater the scale of your application.  :)


Features
------------

* CSS Reset
* HTML5 Element Styling
* Responsive Grid
* Responsive Boxes
* Icons
* Webfonts
* Color Palate
* LESS Templating
* LESS Mixins
* CSS3 Animations

### LESS

Before you can really do anything of real value with Rebar, you need to feel comfortable working with LESS. If you're totally unfamiliar go to http://lesscss.org and read up and find a basic tutorial somewhere. If you're scratching your head and saying WTF? You not be ready to use LESS or Rebar just yet. However, if you want to take your web dev skills to the next level you need to start using LESS or SASS and they will make your life *much* better, I promise.


#### Architecture

* **config.less**

This is where the magic happens. Inspired by the Customize & Theme Generator for Bootstrap, in  **config.less** you define fonts, colors, sizes of your app. By tweaking a few things your app can get quite a custom look and feel going quite easily.


* **css/**
	* app.css
	* guide.css

This is where the actual css files that you load in your web application reside. The **app.css** file is  output from the LESS preprocessor (don't edit this file). The guide file is custom CSS that only pertains to your style guide page- change this to suit your fancy.


* **less/app/** 
	* backgrounds.less
	* fonts.less
	* icons.less
	* messages.less
	* mobile.less
	* tablet.less
	* web.less

This folder contains your application's LESS templates. Add your own files, or modify the exisitng webfonts, icons, and device spefic layouts however you like.


* **less/app.less** 

This file is what creates the final **app.css** that you load in your application. This is where you choose which Rebar components and mixins you want to include. You can also include any number of custom .less files for your application


* **less/rebar/**
	* base.less
	* links.less
	* typography.less
	* navigation.less
	* lists.less
	* elements.less
	* images.less
	* buttons.less
	* forms.less
	* tables.less
	* responsive-grid.less
	* responsive-boxes.less

This folder contains the Rebar LESS templates. By default these files are all included in the **less/app.less** but, you may leave out which ever files your app does not. Example: if you do not use tables leave out **tables.less** to cut down on the final CSS file size.


* **less/mixins/** 
	* animate.less
	* elements.less
	* shapes.less

LESS Mixins are collection of really useful snippets and helpers made by 3rd parties which make doing things like animation, gradients, and shapes really easy. You may not want or need any of these things- in which case just delete these files from your app and delete


What's Missing
--------------------

Rebar would LIKE to be able to easily switch between fixed and fluid grid designs, we don't have this functionality, yet.

At the moment Rebar offers very little aethetics for your site unless you want it to look like the demo page. Thus, if you are not a desiger or are not working with a designer, you may want to use Bootstrap or something else.



Where's the JavaScript?
--------------------------------

If you need a lightbox, dropdown menu, tooltips, typeahead, or snazy Javascript things- you ain't gonna find that here. This is an intentional decision and we don't ever plan to add JS libraries to Rebar. We believe responsive design and the CSS to do so is complex enough to warrant it's own framework- we think libraries and frameworks should never try to do *everything*



### Credits

Brennan Novak creator of [Rebar](https://brennannovak.com)

David Gamache's for creating the [Skeleton Framework](http://www.getskeleton.com)

Dan Eden's awesome [Animate.css](http://daneden.me/animate)

Useful mixins [LESS Elements](http://lesselements.com)

Awesome CSS preprocessor [LESS](http://lesscss.org)