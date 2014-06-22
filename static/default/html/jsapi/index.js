// Make console.log not crash JS browsers that don't support it
if (!window.console) window.console = { log: $.noop, group: $.noop, groupEnd: $.noop, info: $.noop, error: $.noop };


/* **[ Mailpile - OLD LOGIC ]***********************************************

  This will ultimately be replaced / redone with the new_mailpile methods
  below that generated programatically, as it's MOAR BO$$

**************************************************************************** */

function MailPile() {
  this.instance       = {};
	this.search_cache   = [];
	this.messages_cache = [];
  this.messages_composing = {};
	this.tags_cache     = [];
	this.contacts_cache = [];
	this.keybindings    = [
  	["normal", "/",      function() { $("#search-query").focus(); return false; }],
  	["normal", "c",      function() { mailpile.compose(); }],
  	["normal", "g i",    function() { mailpile.go("/in/inbox/"); }],
  	["normal", "g d",    function() { mailpile.go("/in/drafts/"); }],
  	["normal", "g c",    function() { mailpile.go("/contacts/"); }],
  	["normal", "g n c",  function() { mailpile.go("/contacts/add/"); }],
  	["normal", "g t",    function() { mailpile.go("/tag/list/"); }],
  	["normal", "g n t",  function() { mailpile.go("/tag/add/"); }],
  	["normal", "g s",    function() { mailpile.go("/settings/profiles/"); }],
  	["normal", "command+z",  function() { alert('Undo Something ') }],
    ["normal", "s a",    function() { mailpile.bulk_action_select_all(); }],
    ["normal", "s n",    function() { mailpile.bulk_action_select_none(); }],
    ["normal", "s i",    function() { mailpile.bulk_action_select_invert(); }],
    ["normal", "k",      function() { mailpile.bulk_action_selection_down(); }],
    ["normal", "j",      function() { mailpile.bulk_action_selection_up(); }],
    ["normal", "enter",  function() { mailpile.open_selected_thread(); }],
    ["normal", "f",      function() { mailpile.update_search(); }],
  	["normal", ["a"], function() { mailpile.keybinding_move_message(''); }],
  	["normal", ["d"], function() { mailpile.keybinding_move_message('trash'); }],
  	["normal", ["r"], function() { mailpile.bulk_action_read(); }],
  	["normal", ["m s"], function() { mailpile.keybinding_move_message('spam'); }],
  	["normal", ["t"], function() { mailpile.render_modal_tags(); }],
  	["normal", ["u"], function() { mailpile.bulk_action_unread(); }],
    ["global", "esc", function() {
  		$('input[type=text]').blur();
  		$('textarea').blur();
    }]
  ];
	this.commands       = [];
	this.graphselected  = [];
	this.defaults       = {
  	view_size: "comfy"
	}
	this.api = {
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
  	
	}
	this.urls = {
  	message_draft : "/message/draft/=",
  	message_sent  : "/thread/=",
  	tags          : "/tags/"
	}
	this.plugins = [];
};

var mailpile = new MailPile();
var favicon = new Favico({animation:'popFade'});


/* **[ Mailpile - JSAPI ]******************************************************

This file autogenerates JS methods which fire GET & POST calls to Mailpile
API/command endpoints.

It also name-spaces and wraps any and all plugin javascript code.

**************************************************************************** */

/* This is the global mailpile object.

   WARNING: Do not rename! Must match what is defined in the Python code.
*/
var new_mailpile = {
    plugins: {},
    api: {},
    theme: {}
};


/* **[ Mailpile - Theme Settings ]****************************************** */
{% set theme_settings = theme_settings() %}
new_mailpile.theme = {{ theme_settings|json|safe }}


/* **[AJAX Wappers - for the Mailpile API]********************************** */
new_mailpile.api = (function() {
    var api = { {% for command in result.api_methods %}
    {{command.url|replace("/", "_")}}: "/api/0/{{command.url}}/"{% if not loop.last %},{% endif %}

    {% endfor %}
    };

    function action(command, data, method, callback) {
        if (method != "GET" && method != "POST") {
            method = "GET";
        }
        switch (method) {
            case "GET":
                for(var k in data) {
                    if(!data[k] || data[k] == undefined) {
                        delete data[k];
                    }
                }
                var params = $.param(data);
                $.ajax({
                    url      : command + "?" + params,
                    type     : method,
                    dataType : 'json',
                    success  : callback,
                });
                break;
            case "POST":
                $.ajax({
                    url      : command,
                    type     : method,
                    data     : data,
                    dataType : 'json',
                    success  : callback,
                });
                break;
        }

        return true;
    };

    return {
        {%- for command in result.api_methods -%}
        {{command.url|replace("/", "_")}}: function(
            {%- for key in command.query_vars -%}pv_{{key|replace("@", "")}}, {% endfor -%}
            {%- for key in command.post_vars -%}pv_{{key|replace("@", "")|replace(".","_")|replace("-","_")}}, {%- endfor -%} callback) {
            return action(api.{{command.url|replace("/", "_")}}, {
                {%- for key in command.query_vars -%}
                    "{{key}}": pv_{{key|replace("@", "")}},
                {% endfor %}
                {%- for key in command.post_vars -%}
                    "{{key}}": pv_{{key|replace("@", "")}},
                {% endfor %}
            }, "{{command.method}}", callback);
        }{%- if not loop.last -%},{% endif %}

        {% endfor %}
    }
})();


/* Plugin Javascript - we do this in multiple commands instead of one big
   dict, so plugin setup code can reference other plugins. Plugins are
   expected to return a dictionary of values they want to make globally
   accessible.

   FIXME: Make sure the order is somehow sane given dependenies.
*/
{% for js_class in result.javascript_classes %}
new_{{ js_class.classname }} = {% if js_class.code %}(function(){
{{ js_class.code|safe }}})(); /* EOF:{{ js_class.classname }} */
{% else %}{};
{% endif %}
{% endfor %}