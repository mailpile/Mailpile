/* JS App Files */
{% include("jsapi/app/eventlog.js") %}
{% include("jsapi/app/activities.js") %}
{% include("jsapi/app/drag_drop.js") %}
{% include("jsapi/app/global.js") %}
{% include("jsapi/app/keybindings.js") %}
{% include("jsapi/app/notifications.js") %}

/* JS - Crypto */
{% include("jsapi/crypto/gpg.js") %}

/* JS - Compose */
{% include("jsapi/compose/init.js") %}
{% include("jsapi/compose/crypto.js") %}
{% include("jsapi/compose/autosave.js") %}
{% include("jsapi/compose/attachments.js") %}
{% include("jsapi/compose/recipients.js") %}
{% include("jsapi/compose/tooltips.js") %}
{% include("jsapi/compose/events.js") %}
{% include("jsapi/compose/complete.js") %}

/* JS - Contacts */
{% include("jsapi/contacts/display_modes.js") %}
{% include("jsapi/contacts/content.js") %}

/* JS - Search */
{% include("jsapi/search/bulk_actions.js") %}
{% include("jsapi/search/content.js") %}
{% include("jsapi/search/display_modes.js") %}
{% include("jsapi/search/selection_actions.js") %}
{% include("jsapi/search/tooltips.js") %}
{% include("jsapi/search/ui.js") %}

/* JS - Settings */
{% include("jsapi/settings/content.js") %}

/* JS - Tags */
{% include("jsapi/tags/content.js") %}

/* JS - Message */
{% include("jsapi/message/thread.js") %}
{% include("jsapi/message/message.js") %}
{% include("jsapi/message/tooltips.js") %}

/* JS UI Files */
{% include("jsapi/ui/content.js") %}
{% include("jsapi/ui/global.js") %}
{% include("jsapi/ui/topbar.js") %}
{% include("jsapi/ui/sidebar.js") %}
{% include("jsapi/ui/tooltips.js") %}


{% set tags_json = mailpile("tags", "display=*", "mode=flat").result.tags|json %}
$(document).ready(function() {

  // Print JSON for JS Use
  Mailpile.instance['tags'] = {{ tags_json|safe }};

  // Favicon
  var inbox = _.findWhere(Mailpile.instance.tags, {slug: 'inbox'});
  var favicon = new Favico({animation:'popFade'});
  favicon.badge(inbox.stats.new);

  // Show Typeahead
  Mailpile.activities.render_typeahead();

  // Start Eventlog
  //EventLog.init();
  setTimeout(function() {

    // make event log start async (e.g. for proper page load event handling)
    EventLog.timer = $.timer();
    EventLog.timer.set({ time : 22500, autostart : false });
    EventLog.poll();

    // Run Composer Autosave
    if (Mailpile.instance.state.context_url === '/message/' || 
        Mailpile.instance.state.context_url === '/message/draft/') {
      Mailpile.Composer.autosave_timer.play();
      Mailpile.Composer.autosave_timer.set({ time : 20000, autostart : true });
    }

  }, 1000);

});

