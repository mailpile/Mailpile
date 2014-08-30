/* Setup - Complete - Model */
var CompleteModel = Backbone.Model.extend({
  defaults: {
    copying: [
      '{{_("Dont look now, we are copying things")}}',
      '{{_("Copying your mail, please do not be alarmed!")}}',
      '{{_("Copying mail. This could take a while")}}',
      '{{_("Please be patient, we are copying your mail as fast as possible")}}',
      '{{_("You have a lot of mail. I hope you dont have a plane to catch or anything")}}',
      '{{_("Copying mail, put your arms above your head and whistle la cucaracha")}}',
      '{{_("Just making a copy of your mail for ya. Putting it right here in ya inbox, all comfy like")}}'
    ],
    education: [
      '{{_("Mailpile has an advanced tagging system, use Tags to organize and search your mail")}}',
      '{{_("Do you really need to keep all these Amazon Prime shipping confirmations?")}}',
      '{{_("I am pretty sure email from ThinkGeeks 2011 X-mas sale can be deleted.")}}',
      '{{_("Do you really need an email to know when you have been retweeted?")}}',
      '{{_("Email is the largest internet based social network on the planet")}}',
      '{{_("Mailpile uses OpenGPG / PGP to encrypt and decrypt your messages securely")}}',
      '{{_("Which other technology do you use that is 40 years old?")}}',
      '{{_("There are 2.5 billion email users worldwide, thats double the amount of Facebook users!")}}'
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
    ]
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
  show: function() {
    Mailpile.API.settings_set_post({ 'web.setup_complete': true }, function(result) {
      $('#setup').html(_.template($('#template-setup-sources-importing').html(), {}));
    });
  }
});