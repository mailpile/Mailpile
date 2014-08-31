/* Setup - Complete - Model */
var CompleteModel = Backbone.Model.extend({
  defaults: {
    copying: [
      '{{_("Dont look now, we are copying things")}}',
      '{{_("Copying your mail, please do not be alarmed!")}}',
      '{{_("Copying mail. This could take a while")}}',
      '{{_("Please be patient, we are copying mail as fast as possible")}}',
      '{{_("Wow, you have a lot of mail")}}',
      '{{_("I hope you dont have a plane to catch or anything")}}',
      '{{_("Copying mail. Put your arms above your head and whistle la cucaracha")}}',
      '{{_("Making a copy of your mail. Putting it in your inbox, all comfy like")}}'
    ],
    email: [
      '{{_("Mailpile has an advanced tagging system, use Tags to organize and search your mail")}}',
      '{{_("Do you really need to keep all these Amazon Prime shipping confirmations?")}}',
      '{{_("I am pretty sure email from ThinkGeeks 2011 X-mas sale can be deleted.")}}',
      '{{_("Do you really need an email to know when you have been retweeted?")}}',
      '{{_("Email is the largest internet based social network on the planet")}}',
      '{{_("Which other technology do you use that is 40 years old?")}}',
      '{{_("There are 2.5 billion email users worldwide, thats double the amount of Facebook users!")}}'  
    ],
    security: [
      '{{_("Mailpile uses OpenGPG / PGP to encrypt and decrypt your messages securely")}}',
      '{{_("Encrypting emails means your communication actually stays private")}}',
      '{{_("The more encrypted email you send, the better!")}}'
    ],
    jokes: [
      '{{_("Good things come to those who wait")}}',
      '{{_("Make free software and be happy")}}',
      '{{_("Most of Mailpile is made in Iceland, where much of the country believes in elves")}}',
      '{{_("The founders of Mailpile met in a public hot tub in Reykjavík")}}',
      '{{_("Damn kids. Theyre all alike.")}}',
      '{{_("We like volcanos, do you like volcanos?")}}',
      '{{_("A million hamsters are spinning their wheels right now")}}',
      '{{_("Tapping earth for more geothermal energy")}}',
      '{{_("Fortifying encryption shields")}}',
      '{{_("Increasing entropy & scrambling bits")}}',
      '{{_("Digging moat. Filing with alligators. Fortifying walls")}}',
      '{{_("Indexing lovenotes")}}',
      '{{_("Uploading ad keywords to advertisers... doh!")}}',
      '{{_("Crossing out swear words...")}}',
      '{{_("Compiling bullshit bingo grid...")}}',
      '{{_("Abandon all hope, ye who enter here")}}',
      '{{_("Welcome to the nine circles of suffering")}}',
      '{{_("Mailing wife about female contacts")}}',
      '{{_("BCC-ing NSA")}}',
      '{{_("Informing authorities of suspicious activities")}}',
      '{{_("Decrypting an email from Snowden")}}',
      '{{_("Sending encrypted mail to Snowden")}}',
      '{{_("RMS approves!")}}',
      '{{_("Formating your C:\ drive")}}',
      '{{_("Letting you wait for no apparent reason")}}',
      '{{_("What are you wearing?")}}',
      '{{_("Go put the kettle on, this could be a while")}}',
      '{{_("Go get a cup of tea and some biscuits. This will take approximately 4 custard creams worth of time")}}',
      '{{_("Did you know humans share 50 percent of their DNA with a banana? Perverts")}}',
      '{{_("Reticulating Splines")}}',
      '{{_("Estimating chance of astroid hitting Earth")}}',
      '{{_("Looking for heretofore unknown prime numbers")}}',
      '{{_("Reading Terms of Service documents")}}',
      '{{_("Becoming self-aware")}}',
      '{{_("Catching up on shows on Netflix")}}',
      '{{_("Oh, you have some very interesting stuff there")}}',
      '{{_("I think I better understand you better now")}}',
      '{{_("Your past is just a story you tell yourself")}}',
      '{{_("Checking emails for stolen Winklevoss ideas")}}',
      '{{_("Applying coupons...")}}',
      '{{_("Licking stamps...")}}',
      '{{_("Self potato")}}',
      '{{_("Syntax error in line 45 of this e-mail")}}',
      '{{_("Yum yum, that one was tasty")}}',
      '{{_("Hey, there is some Nigerian prince here who wants to give you twenty million dollars...")}}',
      '{{_("How rude!")}}',
      '{{_("Patching bugs...")}}',
      '{{_("Indexing kittens...")}}',
      '{{_("Enhancing photos")}}',
      '{{_("Backing up the entire Internet...")}}',
      '{{_("Really? You are still waiting?")}}',
      '{{_("Well... it sure is a beautiful day")}}',
      '{{_("You should probably go outside or something")}}',
      '{{_("Slacking off over here")}}',
      '{{_("Doing nothing")}}',
      '{{_("Making you wait for no reason")}}',
      '{{_("Testing your patience")}}',
      '{{_("Locating some gigapixels")}}',
      '{{_("Initializing hamsters")}}',
      '{{_("Shoveling more coal into the server")}}',
      '{{_("Calibrating flux capacitors")}}',
      '{{_("Pay no attention to the man behind the curtain")}}',
      '{{_("A few bytes tried to escape, but we caught them")}}',
      '{{_("Verifying local gravitational constant")}}',
      '{{_("This server is powered by a lemon and two electrodes")}}',
      '{{_("You are great just the way you are")}}',
      '{{_("Warning: do not think of purple hippos")}}',
      '{{_("Follow the white rabbit")}}',
      '{{_("Wanna see how deep the rabbit hole goes?")}}',
      '{{_("Re-aligning satellite grid")}}',
      '{{_("Re-routing bitstream")}}',
      '{{_("Supplying monkeys with typewriters")}}',
      '{{_("Warming up particle accelerator")}}',
      '{{_("Time is an illusion. Loading time doubly so")}}',
      '{{_("Waiting for Godot.")}}',
      '{{_("Deterministically simulating future state")}}',
      '{{_("Embiggening prototypes")}}',
      '{{_("Resolving interdependence")}}',
      '{{_("Spinning violently around the y-axis")}}',
      '{{_("Swapping time and space")}}'
    ],
    state: 0
  },
  states: {
    0: 'complete',
    1: 'copying',
    2: 'email',
    3: 'security',
    4: 'jokes'
  },
  icons: {
    0: 'icon-like',
    1: 'icon-inbox',
    2: 'icon-message',
    3: 'icon-lock-closed',
    4: 'icon-star'
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
    if (!StateModel.attributes.complete) {
      Mailpile.API.settings_set_post({ 'web.setup_complete': true }, function(result) {
        $('#setup').html(_.template($('#template-setup-sources-complete').html(), {}));
      });
    } else {
      $('#setup').html(_.template($('#template-setup-sources-complete').html(), {}));
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

    if (last < 4) {
      now = last;
      now++;
    } else {
      last = 4;
      now = 1;
    }

    CompleteView.model.set({ state: now });

    var state_now  = CompleteView.model.states[now];
    var message = _.sample(CompleteView.model.attributes[state_now]);

    var icon_last = CompleteView.model.icons[last];
    var icon_now  = CompleteView.model.icons[now];

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