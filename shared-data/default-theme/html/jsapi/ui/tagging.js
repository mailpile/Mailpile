/* This is shared message tagging/untagging code.
*/
Mailpile.UI.Tagging = (function(){

var operations = {
  'tag':     ['{{_("Tagged 1 message")|escapejs}}',
              '{{_("Tagged (num) messages")|escapejs}}'],
  'untag':   ['{{_("Untagged 1 message")|escapejs}}',
              '{{_("Untagged (num) messages")|escapejs}}'],
  'read':    ['{{_("Marked 1 message read")|escapejs}}',
              '{{_("Marked (num) messages read")|escapejs}}'],
  'unread':  ['{{_("Marked 1 message unread")|escapejs}}',
              '{{_("Marked (num) messages unread")|escapejs}}'],
  'move':    ['{{_("Moved 1 message")|escapejs}}',
              '{{_("Moved (num) messages")|escapejs}}'],
  'archive': ['{{_("Archived 1 message")|escapejs}}',
              '{{_("Archived (num) messages")|escapejs}}'],
  'trash':   ['{{_("Moved 1 message to trash")|escapejs}}',
              '{{_("Moved (num)  messages to trash")|escapejs}}'],
  'unspam':  ['{{_("Moved 1 message out of spam")|escapejs}}',
              '{{_("Moved (num)  messages out of spam")|escapejs}}'],
  'spam':    ['{{_("Moved 1 message to spam")|escapejs}}',
              '{{_("Moved (num) messages to spam")|escapejs}}']
};

/**
 * Tag/untag messages and then update the visible UI to match
 * @param {String|Object} selector - A JQuery selector or DOM element
 * @param {Boolean} [no_callbacks] - Skip invoking callbacks
 * @return {Array} Array of selected values
 */
function tag_and_update_ui(options, op, callback) {
  // If there's nothing to do, don't bother the back-end.
  if (!options.mid) return;
  if (!options.add && !options.del) return;

  var notify_done = Mailpile.notify_working("{{_('Tagging...')|escapejs}}", 500);
  options._error_callback = notify_done;

  Mailpile.API.tag_post(options, function(response) {
{#  // The output of tag_post response.result is:
    // {
    //   "conversations": true, 
    //   "msg_ids": [ ...(list of mids)... ],
    //   "tagged": [
    //     [ { ...(tag info)... }, [ ...(list of mids)... ] ],
    //     ...
    //   ],
    //   "untagged": (same format as tagged),
    //   "state": ...,
    //   "status": "success"
    // }
    //
    // Messages are displayed in different tag contexts and the context
    // determines a) whether the message is displayed (inbox, new, etc),
    // or b) whether tags are listed as labels.
    //
    // Untagging a message means either labels disappear, or the entire
    // message may be gone. Tagging may add labels or change the results
    // of a search - we handle the former here but not the latter.
    //
#}
    notify_done();

    if ((!response.result) || (response.status != "success")) {
      // Just report errors, do nothing else.
      Mailpile.notification(response);
      return;
    }

    var count = response.result.msg_ids.length;
    if (count < 1) return; // This was a no-op.

    // Call callbacks, if any. We do this first, because callbacks may
    // want to reference bits of the DOM that get changed below.
    if (callback) callback(response);

    $('.pile-results').each(function (i, context) {
      var $context = $(context);

      var tids = (($context.data("tids") || "") + "").split(/\s+/);
      var context_tids = {};
      for (var i in tids) { context_tids[tids[i]] = true; }

      for (var i in response.result.untagged) {
        var tag = response.result.untagged[i][0];
        var mids = response.result.untagged[i][1];
        var untagged = {};
        for (var j in mids) { untagged[mids[j]] = true; }

        $context.find('.pile-message').each(function(i, elem) {
          var $elem = $(elem);
          var mid = $elem.data('mid');
          if (untagged[mid]) {
            if (context_tids[tag.tid]) {
              // Message should no longer appear in this context at all
              $elem.slideUp(200, function() { $(this).remove(); });
            }
            else {
              // Remove any tag labels
              $elem.removeClass('in_' + tag.slug)
                   .find('.pile-message-tag-' + tag.tid).remove();

              // Remove tag ID from tids list
              var tids = $elem.data('tids').split(/,/);
              for (var i = tids.length-1; i >= 0; i--) {
                if (tids[i] === tag.tid) tids.splice(i, 1);
              }
              $elem.data('tids', tids.join(','));
            }
          }
        });
      }

      // Add tag labels to elements as necessary
      for (var i in response.result.tagged) {
        var tag = response.result.tagged[i][0];
        if (!context_tids[tag.tid]) {
          var mids = response.result.tagged[i][1];
          var tagged = {};
          for (var j in mids) { tagged[mids[j]] = true; }

          var hex = Mailpile.theme.colors[tag.label_color];
          var tag_html = (
            '<span class="pile-message-tag pile-message-tag-' + 
                          tag.tid + '" style="color: ' + hex + ';">' +
                          '<span class="pile-message-tag-icon ' + tag.icon +
                          '"></span></span>'
          );
          $context.find('.pile-message').each(function(i, elem) {
            var $elem = $(elem);
            var mid = $elem.data('mid');
            if (tagged[mid]) {
              if (tag.flag_hides) {
                // If tag is a hiding tag, make element disappear
                $elem.slideUp(200, function() { $(this).remove(); });
              }
              else {
                $elem.addClass('in_' + tag.slug);
                if (tag.label) {
                  $elem.find('span.item-tags').append(tag_html);
                }
                // Remove tag ID from tids list
                var tids = $elem.data('tids').split(/,/);
                tids.push(tag.tid);
                $elem.data('tids', tids.join(','));
              }
            }
          });
        }
      }

    });

    // Update Bulk UI; do this after a delay, so the fade-outs can complete.
    setTimeout(Mailpile.bulk_actions_update_ui, 300);

    // Override message text if we think we know better
    if (op && operations[op]) {
      if (count == 1) {
        response.message = operations[op][0];
      }
      else {
        var msg = operations[op][1];
        var ofs = msg.indexOf('(num)');
        response.message = (msg.substring(0, ofs) +
                            count +
                            msg.substring(ofs+5));
                        
      }
    }

    // Show notification
    Mailpile.notification(response);
  });
}

return {
  'tag_and_update_ui': tag_and_update_ui
}})();
