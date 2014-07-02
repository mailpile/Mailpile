/* Setup Pages */
var setupdata = {};

/* Welcome - First thing people see */
var Welcome = new Page("#template-setup-welcome", "{{_("Welcome to your")}} <strong>mail</strong>pile");
Welcome.bind_button("#btn-setup-welcome-begin", function() {
  console.log('Go Welcome -> Basic');  
  Welcome.next();
});


/* Basic - Collect */
var Basic = new Page("#template-setup-basic", "{{_("Welcome to Mailpile!")}}");
Basic.bind_button("#btn-setup-basic-info", function(e) {
  e.preventDefault();
  Basic.next();
});


Basic.bind_validator("#input-name-name", function(m) {
  $('#setup-box-basic').removeClass('bounceInRight').addClass('bounceOutLeft');
  console.log('Go Basic -> Dicovery'); 
  return m.value != "";
});

Basic.bind_hide(function() {
	setupdata["name"] = $("#input-name-name").value();
});


/* Discovery - */
var Discovery = new Page("#template-setup-discovery", "{{_("Analyzing your Computer")}}");
Discovery.bind_button("#btn-setup-basic-next", function() {
  console.log('Go Basic -> Crypto');  
  $('#setup-box-discovery').removeClass('bounceInRight').addClass('bounceOutLeft');
  Discovery.next();
});



/* Crypto - Handle keys and such */
var Crypto = new Page("#setup-crypto-setup", "{{_("Welcome to Mailpile!")}}");
Crypto.route("cryptosetup");
Crypto.bind_button("#btn-setup-crypto-prev", function() {
    Crypto.prev();
});


Crypto.bind_button("#btn-setup-crypto-next", function() {
    Crypto.next();
});


/* Wizard order / route table */
var SetupWizard = new Wizard("#setup", "span.title");
SetupWizard.pages = [
	Welcome,
	Basic,
  Discovery,
	Crypto
];

/* Start The Dang thing */
$(document).ready(function() {
    SetupWizard.go();
});