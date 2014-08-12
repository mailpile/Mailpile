// Make console.log not crash JS browsers that don't support it
if (!window.console) window.console = {
    log: $.noop,
    group: $.noop,
    groupEnd: $.noop,
    info: $.noop,
    error: $.noop
};

Mailpile = {
    instance:           {},
    search_target:      'none',
    search_cache:       [],
    messages_cache:     [],
    messages_composing: {},
    crypto_keylookup:   [],
    tags_cache:         [],
    contacts_cache:     [],
    keybindings:        [
        ["normal", "/",      function() { $("#search-query").focus(); return false; }],
        ["normal", "c",      function() { Mailpile.compose(); }],
        ["normal", "g i",    function() { Mailpile.go("/in/inbox/"); }],
        ["normal", "g d",    function() { Mailpile.go("/in/drafts/"); }],
        ["normal", "g c",    function() { Mailpile.go("/contacts/"); }],
        ["normal", "g n c",  function() { Mailpile.go("/contacts/add/"); }],
        ["normal", "g t",    function() { Mailpile.go("/tag/list/"); }],
        ["normal", "g n t",  function() { Mailpile.go("/tag/add/"); }],
        ["normal", "g s",    function() { Mailpile.go("/settings/profiles/"); }],
        ["normal", "h",      function() { Mailpile.go("/help/"); }],
        ["normal", "command+z ctrl+z",  function() { alert('Undo Something ') }],
        ["normal", "space",  function() { Mailpile.bulk_action_select_target(); }],
        ["normal", "s a",    function() { Mailpile.bulk_action_select_all(); }],
        ["normal", "s b",    function() { Mailpile.bulk_action_select_between(); }],
        ["normal", "s n",    function() { Mailpile.bulk_action_select_none(); }],
        ["normal", "s i",    function() { Mailpile.bulk_action_select_invert(); }],
        ["normal", "k",      function() { Mailpile.bulk_action_selection_down(); }],
        ["normal", "j",      function() { Mailpile.bulk_action_selection_up(); }],
        ["normal", "enter",  function() { Mailpile.open_selected_thread(); }],
        ["normal", "f",      function() { Mailpile.update_search(); }],
        ["normal", ["m a"],  function() { Mailpile.keybinding_move_message(''); }],
        ["normal", ["m s"],  function() { Mailpile.keybinding_move_message('spam'); }],
        ["normal", ["m d"],  function() { Mailpile.keybinding_move_message('trash'); }],
        ["normal", ["t"],    function() { Mailpile.render_modal_tags(); }],
        ["normal", ["r"],    function() { Mailpile.bulk_action_read(); }],
        ["normal", ["u"],    function() { Mailpile.bulk_action_unread(); }],
        ["normal", ["up"],   function() { Mailpile.keybinding_target('up'); }],
        ["normal", ["down"], function() { Mailpile.keybinding_target('down'); }],
        ["normal", "shift",  function() { Mailpile.keybinding_shift_router(); }],
        ["global", "esc",    function() {
            $('input[type=text]').blur();
            $('textarea').blur();
        }]
    ],
    commands:         [],
    graphselected:    [],
    defaults: {
        view_size: "comfy"
    },
    api: {
        compose      : "/api/0/message/compose/",
        compose_send : "/api/0/message/update/send/",
        compose_save : "/api/0/message/update/",
        contacts     : "/api/0/search/address/",
        message      : "/api/0/message/=",
        tag          : "/api/0/tag/",
        tag_list     : "/api/0/tags/",
        tag_add      : "/api/0/tags/add/",
        tag_update   : "/api/0/settings/set/",
        search_new   : "/api/0/search/?q=in%3Anew",
        search       : "/api/0/search/",
        settings_add : "/api/0/settings/add/"
    },
    urls: {
        message_draft : "/message/draft/=",
        message_sent  : "/thread/=",
        tags          : "/tags/"
    },
    plugins: [],
    theme: {}
};


/* **[ Mailpile - JSAPI ]******************************************************

This autogenerates JS methods which fire GET & POST calls to Mailpile
API/command endpoints.

It also name-spaces and wraps any and all plugin javascript code.

**************************************************************************** */


/* **[ Mailpile - Theme Settings ]****************************************** */
{% set theme_settings = theme_settings() %}
Mailpile.theme = {{ theme_settings|json|safe }}


/* **[AJAX Wappers - for the Mailpile API]********************************** */
Mailpile.API = {
    _endpoints: {
{% for command in result.api_methods %}
        {{command.url|replace("/", "_")}}_{{command.method|lower}}: "/0/{{command.url}}/"{% if not loop.last %},{% endif %}

{% endfor %}
    },
    _sync_url: "/api",
    _async_url: "/async",
};

Mailpile.API._ajax_error =  function(base_url, command, data, method, response, status) {
    console.log('Oops, an AJAX call returned as error :(');
    console.log('url: ' + base_url + command);
    console.log('method: ' + method);
    console.log(data);
    console.log('status: ' + status);
    console.log(response);
};

Mailpile.API._action = function(base_url, command, data, method, callback) {

    if (method != "GET" && method != "POST") {
        method = "GET";
    }
    if (method == "GET") {
        for(var k in data) {
            if(!data[k] || data[k] == undefined) {
                delete data[k];
            }
        }
        var params = $.param(data);
        $.ajax({
            url      : base_url + command + "?" + params,
            type     : 'GET',
            dataType : 'json',
            success  : callback,
            error: function(response, status) {
              Mailpile.API._ajax_error(base_url, command, data, method, response, status);
            }
        });
    } else if (method =="POST") {
        $.ajax({
            url      : base_url + command,
            type     : 'POST',
            data     : data,
            dataType : 'json',
            success  : callback,
            error    : function(response, status) {
              Mailpile.API._ajax_error(base_url, command, data, method, response, status);
            }
        });
    } else {
      alert('Somethings rotten in Denmark');
    }

    return true;
};

Mailpile.API._sync_action = function(command, data, method, callback) {
  return Mailpile.API._action(Mailpile.API._sync_url, command, data, method, callback);
};

Mailpile.API._async_action = function(command, data, method, callback, flags) {
    function handle_event(data) {
        if (data.result.resultid) {
            subreq = {event_id: data.result.resultid, flags: flags};
            var subid = EventLog.subscribe(subreq, function(ev) {
                callback(ev.private_data, ev);
                if (ev.flags == "c") {
                    EventLog.unsubscribe(data.result.resultid, subid);
                }
            });
        }
    }

    Mailpile.API._action(Mailpile.API._async_url, command, data, method, handle_event, flags);
};

/* Create sync & asyn API commands */
{% for command in result.api_methods -%}
Mailpile.API.{{command.url|replace("/", "_")}}_{{command.method|lower}} = function(data, callback, method) {
    var methods = ["{{command.method}}"];
    if (!method || methods.indexOf(method) == -1) {
        method = methods[0];
    }
    return Mailpile.API._sync_action(
        Mailpile.API._endpoints.{{command.url|replace("/", "_")}}_{{command.method|lower}},
        data,
        method,
        callback
    );
};

Mailpile.API.async_{{command.url|replace("/", "_")}}_{{command.method|lower}} = function(data, callback, method) {
    var methods = ["{{command.method}}"];
    if (!method || methods.indexOf(method) == -1) {
        method = methods[0];
    }
    return Mailpile.API._async_action(
        Mailpile.API._endpoints.{{command.url|replace("/", "_")}}_{{command.method|lower}},
        data,
        method,
        callback
    );
};
{% endfor %}

/* Plugin Javascript - we do this in multiple commands instead of one big
   dict, so plugin setup code can reference other plugins. Plugins are
   expected to return a dictionary of values they want to make globally
   accessible.

   FIXME: Make sure the order is somehow sane given dependenies.
*/
{% for js_class in result.javascript_classes %}
{{ js_class.classname.capitalize() }} = {% if js_class.code %}(function(){
{{ js_class.code|safe }}})(); /* EOF:{{ js_class.classname }} */
{% else %}{};
{% endif %}
{% endfor %}


/* UI - Make fingerprints nicer */
Mailpile.nice_fingerprint = function(fingerprint) {
  // FIXME: I'd really love to make these individual pieces color coded
  // Pertaining to the hex value pairings & even perhaps toggle-able icons
  return fingerprint.split(/(....)/).join(' ');
};
