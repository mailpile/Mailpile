// Make console.log not crash JS browsers that do not support it...
if (!window.console) window.console = {
  log: $.noop,
  group: $.noop,
  groupEnd: $.noop,
  info: $.noop,
  error: $.noop
};


// Mailpile global Javascript state and configuration /========================
Mailpile = {
  csrf_token:         "{{ csrf_token }}",
  ui_in_action:       0,
  instance:           {},
  select_between:     false,
  search_target:      'none',
  search_cache:       [],
  messages_cache:     [],
  messages_composing: {},
  crypto_keylookup:   [],
  tags_cache:         [],
  contacts_cache:     [],
  keybindings:        [
    ["normal", "/",      function() { $("#search-query").focus(); return false; }],
    ["normal", "a c",    function() { Mailpile.UI.Modals.ContactAdd(); }],
    ["normal", "a t",    function() { Mailpile.UI.Modals.TagAdd(); }],
    ["normal", "c",      function() { Mailpile.activities.compose(); }],
    ["normal", "g i",    function() { Mailpile.go("/in/inbox/"); }],
    ["normal", "g d",    function() { Mailpile.go("/in/drafts/"); }],
    ["normal", "g c",    function() { Mailpile.go("/contacts/"); }],
    ["normal", "g n c",  function() { Mailpile.go("/contacts/add/"); }],
    ["normal", "g t",    function() { Mailpile.go("/tags/"); }],
    ["normal", "g n t",  function() { Mailpile.go("/tags/add/"); }],
    ["normal", "g s",    function() { Mailpile.go("/settings/profiles/"); }],
    ["normal", "g h",    function() { Mailpile.go("/help/"); }],
    //["normal", "command+z", function() { alert('Undo Something ') }],
    //["normal", "ctrl+z",    function() { alert('Undo Something ') }],
    //["normal", "shift+[",   function() { alert('Will move up sidebar in:tag list') }],
    //["normal", "shift+]",   function() { alert('Will move down sidebar in:tag list') }],
    //["normal", "command+z", function() { alert('Undo Something ') }],
    ["normal", "space",  function() { Mailpile.bulk_action_toggle_target(); }],
    ["normal", "s a",    function() { Mailpile.bulk_action_select_all(); }],
    ["normal", "s b",    function() { Mailpile.bulk_action_select_between(); }],
    ["normal", "s n",    function() { Mailpile.bulk_action_select_none(); }],
    ["normal", "s i",    function() { Mailpile.bulk_action_select_invert(); }],
    ["normal", "j",      function() { Mailpile.bulk_action_selection_down(); }],
    ["normal", "k",      function() { Mailpile.bulk_action_selection_up(); }],
    ["normal", "enter",  function() { Mailpile.open_selected_thread(); }],
    ["normal", ["m a"],  function() { Mailpile.keybinding_move_message(''); }],
    ["normal", ["m d"],  function() { Mailpile.keybinding_move_message('trash'); }],
    ["normal", ["m s"],  function() { Mailpile.keybinding_move_message('spam'); }],
    ["normal", ["t"],    function() { Mailpile.render_modal_tags(); }],
    ["normal", ["r"],    function() { Mailpile.bulk_action_read(); }],
    ["normal", ["u"],    function() { Mailpile.bulk_action_unread(); }],
    ["normal", ["up"],   function() { Mailpile.keybinding_target('up'); }],
    ["normal", ["down"], function() { Mailpile.keybinding_target('down'); }],
    ["normal", "left",   function() { if ($('#pile-previous').length) { Mailpile.go($('#pile-previous').attr('href'));} }],
    ["normal", "right",  function() { if ($('#pile-next').length) { Mailpile.go($('#pile-next').attr('href'));} }],
    ["global", "esc",    function() {
      $('input[type=text]').blur();
      $('textarea').blur();
    }]
  ],
  nagify: 1000 * 60 * 60 * 24 * 7, // Default nag is 1 per week
  commands:      [],
  graphselected: [],
  defaults: {
    view_size: "comfy",
  },
  config: {
    web: {{config.web|json|safe}}
  },
  api: {
    compose      : "{{ config.sys.http_path }}/api/0/message/compose/",
    compose_send : "{{ config.sys.http_path }}/api/0/message/update/send/",
    compose_save : "{{ config.sys.http_path }}/api/0/message/update/",
    contacts     : "{{ config.sys.http_path }}/api/0/search/address/",
    message      : "{{ config.sys.http_path }}/api/0/message/=",
    tag          : "{{ config.sys.http_path }}/api/0/tag/",
    tag_list     : "{{ config.sys.http_path }}/api/0/tags/",
    tag_add      : "{{ config.sys.http_path }}/api/0/tags/add/",
    tag_update   : "{{ config.sys.http_path }}/api/0/settings/set/",
    search_new   : "{{ config.sys.http_path }}/api/0/search/?q=in%3Anew",
    search       : "{{ config.sys.http_path }}/api/0/search/",
    settings_add : "{{ config.sys.http_path }}/api/0/settings/add/"
  },
  urls: {
    message_draft : "{{ config.sys.http_path }}/message/draft/=",
    message_sent  : "{{ config.sys.http_path }}/thread/=",
    tags          : "{{ config.sys.http_path }}/tags/"
  },
  plugins: [],
  theme: {},
  activities: {},
  local_storage: localStorage || {}
};
{% set theme_settings = theme_settings() %}
Mailpile.theme = {{ theme_settings|json|safe }};


// AJAX Wappers - This is the core Mailpile JS API /==========================
{#
##
## This autogenerates JS methods which fire GET & POST calls to Mailpile
## API/command endpoints.
##
## It also name-spaces and wraps any and all plugin javascript code.
##
#}
Mailpile.API = {
  _endpoints: { {%- for command in result.api_methods %}
    {{command.url|replace("/", "_")}}_{{command.method|lower}}: "/0/{{command.url}}/"{% if not loop.last %},{% endif %}
  {% endfor -%} },
  _sync_url: "{{ config.sys.http_path }}/api",
  _async_url: "{{ config.sys.http_path }}/async",

  _dead_notification: undefined,
  _notify_dead: function(status, message, fullscreen) {
    var advice = ((document.location.href.indexOf('/localhost:') == -1)
                  ? '{{_("Check your network?")|escapejs}}'
                  : '{{_("Restart the app?")|escapejs}}');
    if (fullscreen) {
      if (!$('#connection-down').length) {
        var template = _.template($('#template-connection-down').html());
        $('body').append(template({
          message: message,
          advice: advice
        }));
      }
    }
    else {
      Mailpile.API._dead_notification = Mailpile.notification({
        status: status,
        message: message,
        message2: advice,
        event_id: Mailpile.API._dead_notification,
        icon: 'icon-signature-unknown'
      });
    }
  },
  _ajax_dead_count: 0,
  _ajax_is_alive: function() {
    Mailpile.API._ajax_dead_count = 0;
    if (Mailpile.API._dead_notification) {
      Mailpile.cancel_notification(Mailpile.API._dead_notification);
      Mailpile.API._dead_notification = undefined;
      if ($('#connection-down').length) {
        $('#connection-down').fadeOut().remove();
      }
    }
  },
  _ajax_error: function(base_url, command, data, method, response, status) {
    console.log('Oops, an AJAX call returned as error :(');
    console.log('status: ' + status + ' method: ' + method + ' base_url: ' + base_url + ' command: ' + command);
    console.log(response);

    if (response.status == 403) {
      // We have been logged out or the backend restated, go to login
      var href = document.location.href;
      if (href.indexOf('#') != -1) href = href.substring(0, href.indexOf('#'));
      href += (href.indexOf('?') == -1) ? '?' : '&';
      document.location.href = href + 'ui_relogin=1';
      return;
    }
    else if (response.status == 500) {
      // 500 internal errors and timeouts...
      if (command != '/0/cached/' && command != '/0/eventlog/') {
        Mailpile.notification({
          status: 'error',
          message: '{{_("Oops. Mailpile failed to complete your task.")|escapejs}}',
          icon: 'icon-signature-unknown'
        });
      }
      Mailpile.API._ajax_dead_count = 0;
      return;
    }
    if (response.status == 0 || response.status == 503) {
      // FIXME: 503 actually means pagekite or some other reverse proxy is
      //        down - we tell the user to check the network, but could
      //        probably provide clearer feedback.
      Mailpile.API._ajax_dead_count += 1;
    }

    if (Mailpile.API._ajax_dead_count > 3) {
      Mailpile.API._notify_dead('error', '{{_("Mailpile is unreachable.")|escapejs}}',
                                (Mailpile.API._ajax_dead_count > 10));
    }
    else if (status == "timeout") {
      Mailpile.API._notify_dead('warning', '{{_("Mailpile timed out...")|escapejs}}');
    }
  },

  _action: function(base_url, command, data, method, callback) {
    // Output format, timeout...
    var output = '';
    var timeout = 10000;
    var error_callback = undefined;
    if (data._output) {
      output = data._output;
      delete data['_output'];
    }
    if (data._timeout) {
      timeout = data._timeout;
      delete data['_timeout'];
    }
    if (data._error_callback) {
      error_callback = data._error_callback;
      delete data['_error_callback'];
    }
    if (data._args) {
      for (var i in data._args) {
        command = command + '/' + data._args[i];
      }
      delete data['_args'];
    }

    // Get search context; should be overridden by methods that know better
    var context = (data['context'] || $('#search-query').data('context'));

    // Force method to GET if not POST
    if (method !== 'GET' && method !== 'POST') method = 'GET';

    if (method === 'GET') {
      // Make Querystring
      var params = data._serialized;
      if (!params) {
        for (var k in data) {
          if (!data[k] || data[k] == undefined) {
            delete data[k];
          }
        }
        params = $.param(data);
      }
      if (context && (-1 == params.indexOf('&context=')) &&
                     (0 != params.indexOf('context='))) {
        params += '&context=' + context;
      }

      $.ajax({
        url: base_url + command + output + "?" + params,
        type: 'GET',
        timeout: timeout,
        dataType: 'json',
        success: function(response, status) {
          Mailpile.API._ajax_is_alive();
          return callback(response, status);
        },
        error: function(response, status) {
          Mailpile.API._ajax_error(base_url, command, data,
                                   method, response, status);
          if (error_callback) error_callback(response, status);
        }
      });
    }
    else if (method === 'POST') {
      if (data._serialized) {
        data = data._serialized + '&csrf=' + Mailpile.csrf_token;
        if (context) data = data + '&context=' + context;
      }
      else {
        if (context) data['context'] = context;
        if (data['csrf']) {
          Mailpile.csrf_token = data['csrf'];
        }
        else {
          data['csrf'] = Mailpile.csrf_token;
        }
      }
      $.ajax({
        url: base_url + command + output,
        type: 'POST',
        data: data,
        timeout: timeout,
        dataType: 'json',
        success: function(response, status) {
          Mailpile.API._ajax_is_alive();
          return callback(response, status);
        },
        error: function(response, status) {
          Mailpile.API._ajax_error(base_url, command, data,
                                   method, response, status);
          if (error_callback) error_callback(response, status);
        }
      });
    }
    return true;
  },

  U: function(original_url) {
    var prefix = "{{ config.sys.http_path }}";
    if (original_url.indexOf(prefix) != 0) {
      return prefix + original_url;
    }
    return original_url;
  },

  jhtml_url: function(original_url, rendering) {
    var new_url = original_url;
    var html = new_url.indexOf('.html');
    rendering = rendering || 'minimal';
    if (html != -1) {
      new_url = (new_url.slice(0, html+1) + 'jhtml!' + rendering +
                 new_url.slice(html+5));
    }
    else {
      var qs = new_url.indexOf('?');
      if (qs != -1) {
        new_url = (new_url.slice(0, qs) + 'as.jhtml!' + rendering +
                   new_url.slice(qs));
      }
      else {
        var anch = new_url.indexOf('#');
        if (anch != -1) {
          new_url = (new_url.slice(0, anch) + 'as.jhtml!' + rendering +
                     new_url.slice(anch));
        }
        else {
          new_url += 'as.jhtml!' + rendering;
        }
      }
    }
    return new_url;
  },

  with_template: function(name, action, error, flags) {
      var url = "{{ config.sys.http_path }}/jsapi/templates/" + name + ".html";
      if (flags) {
        url += '?ui_flags=' + flags.replace(' ', '+');
      }
      $.ajax({
        url: url,
        type: 'GET',
        success: function(data) { action(_.template(data)); },
        error: error
      });
  },

  _sync_action: function(command, data, method, callback) {
    return Mailpile.API._action(Mailpile.API._sync_url, command, data, method, callback);
  },

  _async_action: function(command, data, method, callback, flags) {
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
    return Mailpile.API._action(Mailpile.API._async_url, command, data, method, handle_event, flags);
  },

  _method: function(method, methods) {
    if (!method || methods.indexOf(method) == -1) return methods[0];
    return method;
  },
{#- Loop through all commands, creating both sync and async API methods #}
  {%- for command in result.api_methods -%}
    {%- set n = command.url|replace("/", "_") %}
    {%- set m = command.method|lower %}
    {%- set u = command.url %}
    {%- set cm = command.method %}

  {{n}}_{{m}}: function(d,c,m){return Mailpile.API._sync_action("/0/{{u}}/",d,Mailpile.API._method(m,["{{cm}}"]),c);},
  async_{{n}}_{{m}}: function(d,c,m){return Mailpile.API._async_action("/0/{{u}}/",d,Mailpile.API._method(m,["{{cm}}"]),c);}{% if not loop.last %},{% endif %}
  {% endfor %}

};


// JS App Files /=============================================================
{% include("jsapi/global/eventlog.js") %}
{% include("jsapi/global/activities.js") %}
{% include("jsapi/global/global.js") %}
{% include("jsapi/global/helpers.js") %}
{% include("jsapi/global/silly.js") %}


// JS - UI /==================================================================
{% include("jsapi/ui/init.js") %}
{% include("jsapi/ui/notifications.js") %}
{% include("jsapi/ui/selection.js") %}
{% include("jsapi/ui/tagging.js") %}
{% include("jsapi/ui/content.js") %}
{% include("jsapi/ui/global.js") %}
{% include("jsapi/ui/topbar.js") %}
{% include("jsapi/ui/sidebar.js") %}
{% include("jsapi/ui/tooltips.js") %}
{% include("jsapi/ui/keybindings.js") %}
{% include("jsapi/ui/events.js") %}


// Plugin Javascript /========================================================
{#
## Note: we do this in multiple commands instead of one big dict, so plugin
## setup code can reference other plugins. Plugins are expected to return a
## dictionary of values they want to make globally accessible.
##
## FIXME: Make sure the order is somehow sane given dependenies.
#}
{% for js_class in result.javascript_classes %}
{% set js_classname = js_class.classname.capitalize() -%}
{% if js_class.code -%}
{{ js_classname }} = (function(){
{{ js_class.code|safe }}
})(); // End of {{ js_classname }} /----------- ---- --- -- -

{% else -%}
{{ js_classname }} = {};
{% endif %}
{% endfor %}

// EOF
