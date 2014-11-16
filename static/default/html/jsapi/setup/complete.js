/* Setup - Complete - Model */
var CompleteModel = Backbone.Model.extend({
  defaults: {
    copying: [
      '{{_("Mail is being imported into your Mailpile")}}',
      '{{_("Dont look now, we are copying things")}}',
      '{{_("Copying your mail, please do not be alarmed!")}}',
      '{{_("Copying mail. This could take a while")}}',
      '{{_("Please be patient, we are copying mail as fast as possible")}}',
      '{{_("Wow, you have a lot of mail")}}',
      '{{_("I hope you dont have a plane to catch or anything")}}',
      '{{_("Copying mail. Put your arms above your head and whistle la cucaracha")}}',
      '{{_("Making a copy of your mail. Putting it in your inbox, all comfy like")}}'
    ],
    nerds: [
      '{{_("Damn kids. Theyre all alike.")}}',
      '{{_("RMS approves!")}}',
      '{{_("Formating your C:\ drive")}}',
      '{{_("Fortifying encryption shields")}}',
      '{{_("Increasing entropy & scrambling bits")}}',
      '{{_("Patching bugs...")}}',
      '{{_("Indexing kittens...")}}',
      '{{_("Indexing lovenotes")}}',
      '{{_("Reticulating Splines")}}',
      '{{_("Syntax error in line 45 of this e-mail")}}',
      '{{_("Shoveling more coal into the server")}}',
      '{{_("Calibrating flux capacitors")}}',
      '{{_("A few bytes tried to escape, but we caught them")}}',
      '{{_("Deterministically simulating future state")}}',
      '{{_("Embiggening prototypes")}}',
      '{{_("Resolving interdependence")}}',
      '{{_("Spinning violently around the y-axis")}}',
      '{{_("Locating additional gigapixels")}}',
      '{{_("Initializing hamsters")}}',
      '{{_("This is our world now... the world of the electron and the switch")}}',
      '{{_("Uploading ad keywords to advertisers... doh!")}}',
      '{{_("Becoming self-aware")}}',
      '{{_("Looking for heretofore unknown prime numbers")}}',
      '{{_("Re-aligning satellite grid")}}',
      '{{_("Re-routing bitstream")}}',
      '{{_("Warming up particle accelerator")}}',
      '{{_("Time is an illusion. Loading time doubly so")}}',
      '{{_("Verifying local gravitational constant")}}',
      '{{_("This server is powered by a lemon and two electrodes")}}'
    ],
    email: [
      '{{_("Mailpile has an advanced tagging system & search engine at its core")}}',
      '{{_("Do you really need to keep all these Amazon Prime shipping confirmations?")}}',
      '{{_("I am pretty sure email from ThinkGeeks 2011 X-mas sale can be deleted.")}}',
      '{{_("Do you really need an email to know when you have been retweeted?")}}',
      '{{_("Email is the largest internet based social network on the planet")}}',
      '{{_("Which other technology do you use that is 40 years old?")}}',
      '{{_("There are 2.5 billion email users worldwide, thats double the amount of Facebook users!")}}',
      '{{_("Use Mailpile Tags to better organize and search your mail")}}',
      '{{_("Remember getting your first email address? Remember how it felt like something private?")}}',
      '{{_("Email is a decentralized by design, this means no one company or government owns it!")}}',
      '{{_("Over 100 trillion emails are sent per year, wow!")}}',
      '{{_("Email is the most widely used communication protocol ever created by humans")}}',
      '{{_("Email uses an open standard agreed upon by the entire world & owned by no one")}}'
    ],
    security: [
      '{{_("BCC-ing the NSA and GCHQ")}}',
      '{{_("Sending encrypted mail to Snowden")}}',
      '{{_("Decrypting an email from Snowden")}}',
      '{{_("The worlds most powerful governments are conducting mass dragnet surveillance")}}',
      '{{_("Most email can be read by anyone as it travel through the internet")}}',
      '{{_("Encryption ensures that your emails are only read by the intended recipient")}}',
      '{{_("Unencrypted email is more like sending a postcard than sending a letter")}}',
      '{{_("Mailpile uses OpenPGP to encrypt and decrypt your messages securely")}}',
      '{{_("All of your config settings & passwords are encrypted with AES 256")}}',
      '{{_("Encrypting emails means your communication actually stays private")}}',
      '{{_("The more encrypted email you send, the better!")}}',
      '{{_("Make sure you print or save your keys & passphrase somewhere securely")}}',
      '{{_("Mailpile by default encrypts your search index!")}}',
      '{{_("The most common Email password is 123456, hopefully yours is different")}}'
    ],
    jokes: [
      '{{_("Good things come to those who wait")}}',
      '{{_("Make free software and be happy")}}',
      '{{_("Most of Mailpile was built from cafes in Reykjavík, Iceland")}}',
      '{{_("Many Icelanders believe in elves and magical hidden people")}}',
      '{{_("The founders of Mailpile first met in a public hot tub in Reykjavík")}}',
      '{{_("We like volcanos, do you like volcanos?")}}',
      '{{_("A million hamsters are spinning their wheels right now")}}',
      '{{_("Tapping earth for more geothermal energy")}}',
      '{{_("Digging moat. Filing with alligators. Fortifying walls")}}',
      '{{_("Crossing out swear words...")}}',
      '{{_("Compiling bullshit bingo grid...")}}',
      '{{_("Abandon all hope, ye who enter here")}}',
      '{{_("Welcome to the nine circles of suffering")}}',
      '{{_("Mailing wife about female contacts")}}',
      '{{_("Informing authorities of suspicious activities")}}',
      '{{_("Letting you wait for no apparent reason")}}',
      '{{_("What are you wearing?")}}',
      '{{_("Go put the kettle on, this could be a while")}}',
      '{{_("Go get a cup of tea and some biscuits. This will take approximately 4 custard creams worth of time")}}',
      '{{_("Did you know humans share 50 percent of their DNA with a banana? Perverts")}}',
      '{{_("Estimating chance of astroid hitting Earth")}}',
      '{{_("Reading Terms of Service documents")}}',
      '{{_("Catching up on shows on Netflix")}}',
      '{{_("Oh, you have some very interesting old emails")}}',
      '{{_("I think I better understand you now")}}',
      '{{_("Your past is just a story you tell yourself")}}',
      '{{_("Checking emails for stolen Winklevoss ideas")}}',
      '{{_("Applying coupons...")}}',
      '{{_("Licking stamps...")}}',
      '{{_("Self potato")}}',
      '{{_("Yum yum, that one was tasty")}}',
      '{{_("Hey, there is some Nigerian prince here who wants to give you twenty million dollars...")}}',
      '{{_("How rude!")}}',
      '{{_("Now enhancing photos")}}',
      '{{_("Backing up the entire Internet...")}}',
      '{{_("Really? You are still waiting?")}}',
      '{{_("Well... it sure is a beautiful day")}}',
      '{{_("You should probably go outside or something")}}',
      '{{_("Slacking off over here")}}',
      '{{_("Doing nothing")}}',
      '{{_("Making you wait for no reason")}}',
      '{{_("Testing your patience")}}',
      '{{_("Pay no attention to the man behind the curtain")}}',
      '{{_("You are great just the way you are")}}',
      '{{_("Warning: do not think of purple hippos")}}',
      '{{_("Follow the white rabbit")}}',
      '{{_("Wanna see how deep the rabbit hole goes?")}}',
      '{{_("Supplying monkeys with typewriters")}}',
      '{{_("Waiting for Godot.")}}',
      '{{_("Swapping time and space")}}'
    ],
    state: 0
  },
  states: {
    0: 'complete',
    1: 'copying',
    2: 'nerds',
    3: 'email',
    4: 'security',
    5: 'jokes'
  },
  icons: {
    0: 'icon-like',
    1: 'icon-inbox',
    2: ['icon-trophy', 'icon-robot', 'icon-graph'],
    3: ['icon-inbox', 'icon-tag', 'icon-compose', 'icon-search'],
    4: ['icon-privacy', 'icon-lock-closed', 'icon-key'],
    5: ['icon-star', 'icon-lightbulb', 'icon-new', 'icon-donate']
  }
});


/* Setup - Complete - View */
var CompleteView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function(){
    return this;
  },
  events: {
    "click #setup-complete-tour-start": "showTour"
  },
  show: function() {
    var complete_template = _.template($('#template-setup-sources-complete').html());

    if (!StateModel.attributes.complete) {
      Mailpile.API.settings_set_post({ 'web.setup_complete': true }, function(result) {
        $('#setup').html(complete_template({}));
      });
    } else {
      $('#setup').html(complete_template({}));
    }
  },
  showTour: function(e) {

    e.preventDefault();

    // Topbar
    $('#header').addClass('animated bounceOutUp');

    setTimeout(function() {
      $('#header').remove();
      var header_html = $('#template-setup-topbar').html();
      $('body').prepend(header_html).find('#header').addClass('animated bounceInDown');
    }, 500);

    // Navigation
    $('#setup-complete-waiting').removeClass('fadeIn').addClass('bounceOutDown');

    setTimeout(function() {
      $('#setup-complete-waiting').remove();
      $('#setup-complete-explore').removeClass('hide').addClass('bounceInUp');
    }, 1000);
  },
  showProcessingMessage: function() {

    // Select Message
    var last = CompleteView.model.get('state');
    var now = 0;

    if (last < 5) {
      now = last;
      now++;
    } else {
      last = 5;
      now = 1;
    }

    CompleteView.model.set({ state: now });

    var state_now = CompleteView.model.states[now];
    var message   = _.sample(CompleteView.model.attributes[state_now]);

    var icon_last = CompleteView.model.icons[last];
    var icon_now  = CompleteView.model.icons[now];

    if (_.isArray(icon_last)) {
      icon_last = icon_last.join(' ');
    }
    if (_.isArray(icon_now)) {
      icon_now = _.sample(icon_now);
    }

    // Update with live data
    var copying = 'Copying [LIVE DATA] Mail';

    $('#setup-complete-icon').removeClass('fadeIn').addClass('bounceOutRight');
    $('#setup-complete-message').removeClass('fadeIn').addClass('bounceOutRight');
    $('#setup-complete-copying').removeClass('fadeIn').addClass('bounceOutRight');

    setTimeout(function() {
      $('#setup-complete-icon').removeClass('bounceOutRight ' + icon_last).addClass('fadeIn ' + icon_now);
      $('#setup-complete-message').html(message).removeClass('bounceOutRight').addClass('fadeIn');
      $('#setup-complete-copying').html(copying).removeClass('bounceOutRight').addClass('fadeIn');
    }, 750);
  }
});