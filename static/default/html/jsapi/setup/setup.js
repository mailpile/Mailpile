/* Setup Pages */
var setupdata = {};

/* Welcome - First thing people see */
var Welcome = new Page("#template-setup-welcome", "{{_("Welcome to your")}} <strong>mail</strong>pile");
Welcome.bind_button("#btn-setup-welcome-begin", function() {
  console.log('Go Welcome -> Basic');  
  Welcome.next();
});


/* Basic - Collect name + password */
var Basic = new Page("#template-setup-basic", "{{_("Welcome to Mailpile!")}}");
Basic.bind_button("#btn-setup-basic-info", function(e) {
  e.preventDefault();
  console.log('Go Basic -> Discovery');
  $('#setup-box-basic').removeClass('bounceInRight').addClass('bounceOutLeft');
  setTimeout(function() {
    Basic.next()
  }, 500);    
});

/*
Basic.bind_validator("#input-name-name", function(m) {
  $('#setup-box-basic').removeClass('bounceInRight').addClass('bounceOutLeft');
  console.log('Go Basic -> Dicovery'); 
  return m.value != "";
});

Basic.bind_hide(function() {
	setupdata["name"] = $("#input-name-name").value();
});
*/


/* Discovery - Find things like keychain mail sources on disk */
var Discovery = new Page("#template-setup-discovery", "{{_("Analyzing your Computer")}}");

Discovery.bind_show(function(page) {
  setTimeout(function() {
    $('#btn-setup-discovery').fadeIn('normal');
  }, 1500);
});

Discovery.bind_button("#btn-setup-discovery", function(e) {
  console.log('Go Discovery -> Crypto');
  e.preventDefault();
  //$('#setup-box-discovery').removeClass('bounceInRight').addClass('bounceOutLeft');
  Discovery.next();
});


/* Crypto - Handle keys and such */
var CryptoFound = new Page("#template-setup-crypto-found-keys", "{{_("Setting Security")}}", {
  public_key_count: 0,
  private_key_count: 0
});

CryptoFound.bind_button("#btn-setup-crypto-import", function(e) {
  console.log('Go Crypto -> Source Local');
  e.preventDefault();
  CryptoFound.next();
});

CryptoFound.bind_show(function(page) {
  Mailpile.API.setup_check_keychain({ testing: 'Yes'}, function(response) {
    console.log(response.result);
    $('#setup-crypto-public-key-count').html(response.result.public_keys);
    $('#setup-crypto-private-key-count').html(response.result.private_keys);
  });
});


/* Source Local - Show & import local mail sources */
var SourceLocal = new Page("#template-setup-source-local", "Discovered Local Mail", {
  source_type: "Thunderbird",
  source_items: [{
      name: "Friends & Family",
      count: 3672,
      path: "/Users/brennannovak/Library/Mail/Folders/friends-family.mbox"
    },{
      name: "Work Stuff",
      count: 7271,
      path: "/Users/brennannovak/Library/Mail/Folders/work-stuff.mbox"
    },{
      name: "Conferences",
      count: 392,
      path: "/Users/brennannovak/Library/Mail/Folders/conferences.mbox"
    },{
      name: "Important Stuff",
      count: 1739,
      path: "/Users/brennannovak/Library/Mail/Folders/important-stuff.mbox"
    },{
      name: "Really Important Stuff",
      count: 445,
      path: "/Users/brennannovak/Library/Mail/Folders/really-important-stuff.mbox"
    },{
      name: "Old Archive",
      count: 128342,
      path: "/Users/brennannovak/Library/Mail/Folders/old-archive.mbox"
    }
  ]
});

SourceLocal.bind_show(function(page) {
  console.log('inside of SourceLocal.bind_hide() awwww');
  // FIXME: using temp JS data
  $.each(page.data.source_items, function(key, value) {
    var html = '<tr><td>' + value.name + '<span>' + value.count + '<span><br>' + value.path + '</td><td><input type="checkbox"></td></tr>';
    $('#setup-source-local-items').append(html);
  });
});

SourceLocal.bind_button("#btn-setup-source-local", function(e) {
  console.log('Source Local -> Source Settings');
  e.preventDefault();
  SourceLocal.next();
});


/* Source Settings - Settings for mail sources */
var SourceLocalSettings = new Page("#template-setup-source-local-settings", "Configure Mail Source", {
  source_type: "Thunderbird"
});

SourceLocalSettings.bind_button("#btn-setup-source-local-settings", function(e) {
  console.log('Source Local Settings -> Source Remote');
  e.preventDefault();
  SourceLocalSettings.next();
});



/* Source Remote - Add remote mail sources */
var SourceRemote = new Page("#template-setup-source-remote", "Add Remote Sources", {});

SourceRemote.bind_button("#btn-setup-source-remote", function(e) {
  console.log('Source Remote -> Source Settings');
  e.preventDefault();
  SourceRemote.next();
});


/* Source Settings - Settings for mail sources */
var SourceRemoteSettingsData = {
  source_type: "Gmail"
};

var SourceRemoteSettings = new Page("#template-setup-source-remote-settings", "Configure Mail Source", SourceRemoteSettingsData);

SourceRemoteSettings.bind_button("#btn-setup-source-remote", function(e) {
  console.log('Source Remote Settings -> Source');
  e.preventDefault();
  SourceRemoteSettings.next();
});


/* Wizard order / route table */
var SetupWizard = new Wizard("#setup", "span.title");
SetupWizard.pages = [
	Welcome,
	Basic,
  Discovery,
	CryptoFound,
  SourceLocal,
  SourceLocalSettings,
  SourceRemote,
  SourceRemoteSettings
];
