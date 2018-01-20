/* JS - Crypto */
{% include("jsapi/crypto/init.js") %}
{% include("jsapi/crypto/events.js") %}
{% include("jsapi/crypto/find.js") %}
{% include("jsapi/crypto/import.js") %}
{% include("jsapi/crypto/modals.js") %}
{% include("jsapi/crypto/tooltips.js") %}
{% include("jsapi/crypto/ui.js") %}

/* JS - Compose */
{% include("jsapi/compose/init.js") %}
{% include("jsapi/compose/crypto.js") %}
{% include("jsapi/compose/autosave.js") %}
{% include("jsapi/compose/attachments.js") %}
{% include("jsapi/compose/recipients.js") %}
{% include("jsapi/compose/modals.js") %}
{% include("jsapi/compose/tooltips.js") %}
{% include("jsapi/compose/events.js") %}
{% include("jsapi/compose/complete.js") %}
{% include("jsapi/compose/body.js") %}

/* JS - Contacts */
{% if 0 and is_dev_version() %}
{% include("jsapi/contacts/init.js") %}
{% include("jsapi/contacts/display_modes.js") %}
{% include("jsapi/contacts/events.js") %}
{% include("jsapi/contacts/modals.js") %}
{% endif %}

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
{% include("jsapi/tags/modals.js") %}
{% include("jsapi/tags/events.js") %}

/* JS - Message */
{% include("jsapi/message/init.js") %}
{% include("jsapi/message/events.js") %}
{% include("jsapi/message/message.js") %}
{% include("jsapi/message/html-sandbox.js") %}
{% include("jsapi/message/tooltips.js") %}
{% include("jsapi/message/ui.js") %}

