var setupdata = {};

var WelcomePage = new Page("#mailpile_welcome_page");
WelcomePage.bind_button("#btn_mailpile_welcome_page_start", function() { WelcomePage.next(); });

var NamePage = new Page("#mailpile_name_page");
NamePage.bind_button("#btn_mailpile_name_page_next", function() { NamePage.next(); });
NamePage.bind_validator("#input_name_page_name", function(m) { return m.value != ""; });
NamePage.bind_hide(function() {
	setupdata["name"] = $("#input_name_page_name").value();
});

var CryptoPage = new Page("#mailpile_crypto_setup");
CryptoPage.route("cryptosetup");
CryptoPage.bind_button("#btn_mailpile_crypto_page_prev", function() { CryptoPage.prev(); });
CryptoPage.bind_button("#btn_mailpile_crypto_page_next", function() { CryptoPage.next(); });

var SetupWizard = new Wizard();
SetupWizard.pages = [
	WelcomePage,
	CryptoPage,
];

SetupWizard.go();
