/* Mailpile.plugins.hints */
// SPDX-FileCopyrightText: 2011-2015  Bjarni R. Einarsson, Mailpile ehf and friends
// SPDX-License-Identifier: AGPL-3.0-or-later

$(document).ready(function() {
  // Display initial hint randomly 1 to 5 minutes after page load
  setTimeout(Mailpile.plugins.hints.hint, (1 + 4 * Math.random()) * 60000);
});

return {
  hint: function() {
    // Check for new hints every 3.5 - 4.5 hours
    setTimeout(Mailpile.plugins.hints.hint, (3.5 + Math.random()) * 3600000);

    // Using the POST method will record the hint as having been displayed.
    // FIXME: Should we use GET, and then POST if the user interacts?
    Mailpile.API.logs_hints_post({
      now: true,
    }, function(response) {
      if (response.result.hints.length) {
        var hint = response.result.hints[0];
        hint['status'] = 'info';
        hint['icon'] = 'icon-lightbulb';
        if (hint['action_url'].indexOf('javascript:') != 0) {
          hint['action_url'] = Mailpile.API.U(hint['action_url']);
        }
        Mailpile.notification(hint);
      }
    });
  },
  release_notes: function(ev) {
    $('#release_notes').eq(0).trigger('click');
  },
  keybindings: function() {
    Mailpile.display_keybindings();
  },
};

