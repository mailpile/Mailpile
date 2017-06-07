/* Topbar - Search - Focus */
$(document).on('focus', '#search-query', function() {
  $(this).select();
});


/* Clear button */

Mailpile.UI.set_clear_state = setClarState = function(queryBox){
  var $clearButton = $(queryBox).next('.clear-search');
  if (queryBox.value.length > 0) {
    $clearButton.show();
  } else{
    $clearButton.hide();
  }
};

$(function(){
  var queryBox = $('#search-query');
  if (queryBox.length) {
    Mailpile.UI.set_clear_state(queryBox[0]);
  }
});

$(document).on('input change', '#search-query', function(e) {
  Mailpile.UI.set_clear_state(e.target);
});

$(document).on('click', '#form-search .clear-search', function(e) {
  var dflt = $('#search-query').data('q');
  if ($('#search-query').val() == dflt) {
    $('#search-query').val('').focus();
    $(e.target).hide();
  }
  else {
    $('#search-query').val(dflt).focus();
  }
});

/* Search - Special handling of certain queries */
$(document).on('submit', '#form-search', function(event) {
  var commands = {
    in: function(cmdArgs) {
      // TODO: Check against whitelist of available inboxes?
      var inbox = cmdArgs[0];
      Mailpile.go("/in/" + inbox + "/");
    },
    // TODO: The tags endpoint does not seem to work?
    // tags: function(cmdArgs) {
    //   // TODO: Check against whitelist of available tags?
    //   var tag = cmdArgs[0];
    //   // TODO: Use a specific method instead?
    //   $.getJSON("{{ config.sys.http_path }}/tags/" + tag + "/as.jhtml", function(data) {
    //     $("#content-wide").html(data.result);
    //   });
    // },
    // TODO: I could not get this endpoint to match/find any keys
    keys: function(cmdArgs) {
      var keyQuery = cmdArgs.join(" ");
      Mailpile.UI.Modals.CryptoFindKeys({
        query: keyQuery
      });
    },
  };

  var searchQuery = $("#search-query").val().trim();
  var isQueryCliCommand = searchQuery.startsWith("/");

  var queryParts = searchQuery.split(":");
  var queryCommand = queryParts[0];
  var queryOptArgs = queryParts[1] || "";
  var cmdArgs = queryOptArgs.trim().split(" ");
  var isQueryIncludingValidCommand = (typeof commands[queryCommand] === "function");

  if (isQueryCliCommand === true) {
    // TODO: Implement cli command handling here
    // event.preventDefault();
  } else if (isQueryIncludingValidCommand === true) {
    event.preventDefault();
    var command = commands[queryCommand];
    command.call(this, cmdArgs);
  } else {
    event.preventDefault();
    var autoajaxSearchQuery = "";
    autoajax_go("/search/?q=" + searchQuery);
  }
});


// {# FIXME: Disabled by Bjarni, this doesn't really work reliably
//  #
/* Activities - */
$(document).on('click', '#button-search-options', function(key) {
	$('#search-params').slideDown('fast');
});
/* Activities - */
$(document).on('blur', '#button-search-options', function(key) {
	$('#search-params').slideUp('fast');
});
// #
// #}
// #

Mailpile.UI.content_setup.push(function($content) {
  // FIXME: This will do silly things if we have multiple search results
  //        on a page at a time.
  var $sq = $('#search-query');
  var $st = $content.find('#search-terms');
  var search_terms = $st.data('q');
  if (!search_terms) search_terms = '';
  if (($sq.data('q') == $sq.val()) || ($sq.val() == "")) {
    $sq.val(search_terms);
  }
  $sq.data('q', search_terms).data('context', $st.data('context'));
  Mailpile.UI.set_clear_state($sq[0]);
});
