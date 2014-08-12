{% set tags_json = mailpile("tags", "display=*", "mode=flat").result.tags|json %}
$(document).ready(function() {

  // Print JSON for JS Use
  Mailpile.instance['tags'] = {{ tags_json|safe }};

  var inbox = _.findWhere(Mailpile.instance.tags, {slug: 'inbox'});
  var favicon = new Favico({animation:'popFade'});
  favicon.badge(inbox.stats.new);
});


/* JS App Files */
{% include("jsapi/app/activities.js") %}
{% include("jsapi/app/drag_drop.js") %}
{% include("jsapi/app/global.js") %}
{% include("jsapi/app/keybindings.js") %}
{% include("jsapi/app/notifications.js") %}

/* JS - Crypto */
{% include("jsapi/crypto/gpg.js") %}

/* JS - Compose */
{% include("jsapi/compose/crypto.js") %}
{% include("jsapi/compose/autosave.js") %}
{% include("jsapi/compose/attachments.js") %}
{% include("jsapi/compose/content.js") %}
{% include("jsapi/compose/tooltips.js") %}
{% include("jsapi/compose/ui.js") %}

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
