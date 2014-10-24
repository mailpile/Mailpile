/* JS App Files */
{% include("jsapi/global/eventlog.js") %}
{% include("jsapi/global/activities.js") %}
{% include("jsapi/global/global.js") %}
{% include("jsapi/global/keybindings.js") %}
{% include("jsapi/global/notifications.js") %}

/* JS - UI */
{% include("jsapi/ui/init.js") %}
{% include("jsapi/ui/content.js") %}
{% include("jsapi/ui/events.js") %}
{% include("jsapi/ui/global.js") %}
{% include("jsapi/ui/topbar.js") %}
{% include("jsapi/ui/sidebar.js") %}
{% include("jsapi/ui/tooltips.js") %}

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
{% include("jsapi/compose/body.js") %}

/* JS - Contacts */
{% include("jsapi/contacts/init.js") %}
{% include("jsapi/contacts/display_modes.js") %}
{% include("jsapi/contacts/content.js") %}

/* JS - Search */
{% include("jsapi/search/init.js") %}
{% include("jsapi/search/bulk_actions.js") %}
{% include("jsapi/search/events.js") %}
{% include("jsapi/search/display_modes.js") %}
{% include("jsapi/search/selection_actions.js") %}
{% include("jsapi/search/tooltips.js") %}
{% include("jsapi/search/ui.js") %}

/* JS - Settings */
{% include("jsapi/settings/content.js") %}

/* JS - Tags */
{% include("jsapi/tags/init.js") %}
{% include("jsapi/tags/content.js") %}

/* JS - Message */
{% include("jsapi/message/init.js") %}
{% include("jsapi/message/events.js") %}
{% include("jsapi/message/message.js") %}
{% include("jsapi/message/tooltips.js") %}
{% include("jsapi/message/ui.js") %}

