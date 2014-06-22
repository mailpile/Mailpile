/*  */
var setupdata = {};

/* Welcome - First thing people see */
var WelcomePage = new Page("#template-setup-welcome", "{{_("Welcome to Mailpile!")}}");
WelcomePage.bind_button("#btn-setup-welcome-begin", function() {
    console.log('Go from Welcome -> Basic');  
    WelcomePage.next();
});

/* Basic - Collect */
var BasicPage = new Page("#template-setup-basic", "{{_("Basic information")}}");
BasicPage.bind_button("#btn-setup-basic-next", function() {
    console.log('Go from Basic -> Crypto');  
    BasicPage.next();
});

BasicPage.bind_validator("#input-name-name", function(m) {
    return m.value != "";
});

BasicPage.bind_hide(function() {
	setupdata["name"] = $("#input-name-name").value();
});


var CryptoPage = new Page("#setup-crypto-setup");
CryptoPage.route("cryptosetup");
CryptoPage.bind_button("#btn-setup-crypto-prev", function() {
    CryptoPage.prev();
});


CryptoPage.bind_button("#btn-setup-crypto-next", function() {
    CryptoPage.next();
});


/* Wizard order / route table */
var SetupWizard = new Wizard("#setup", "span.title");
SetupWizard.pages = [
	WelcomePage,
	BasicPage,
	CryptoPage
];

/* Start The Dang thing */
$(document).ready(function() {
    SetupWizard.go();
});