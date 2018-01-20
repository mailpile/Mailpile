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
  search_target:      'none',
  messages_composing: {},
  crypto_keylookup:   [],
  keybindings:        [ {#
    // Note to hackers:
    //
    // We avoid binding TAB, ENTER, UP, DOWN and SPACE because those all have
    // meaning in common browser defaults. We aim to play nice with browser
    // defaults, not end up in a preventDefault war.
    //
    // See also: https://github.com/mailpile/Mailpile/issues/1814
    //
    // #}
    { title: '{{_("Search mail")|escapejs}}',         keys: "/",       callback: function(e) { $("#search-query").focus(); return false; } },
    { title: '{{_("Compose e-mail")|escapejs}}',      keys: "c",       callback: function(e) { Mailpile.activities.compose(); }},
    { title: '{{_("Move selection down")|escapejs}}', keys: "j",       callback: function(e) { Mailpile.keybinding_selection_down(); }},
    { title: '{{_("Extend selection down")|escapejs}}', keys: "x",     callback: function(e) { Mailpile.keybinding_selection_extend(); }},
    { title: '{{_("Move selection up")|escapejs}}',   keys: "k",       callback: function(e) { Mailpile.keybinding_selection_up(); }},
    { title: '{{_("Previous page of results")|escapejs}}', keys: "h",  callback: function(e) { $('#pile-previous').eq(0).trigger('click'); }},
    { title: '{{_("Next page of results")|escapejs}}', keys: "l",      callback: function(e) { $('#pile-next').eq(0).trigger('click'); }},
    { title: '{{_("Open e-mail for reading")|escapejs}}', keys: "o",   callback: function(e) { Mailpile.open_or_close_selected_thread(); }},
    { title: '{{_("Go to Inbox")|escapejs}}',         keys: "g i",     callback: function(e) { Mailpile.go("/in/inbox/"); }},
    { title: '{{_("Go to Drafts")|escapejs}}',        keys: "g d",     callback: function(e) { Mailpile.go("/in/drafts/"); }},
    { title: '{{_("Go to Outbox")|escapejs}}',        keys: "g o",     callback: function(e) { Mailpile.go("/in/outbox/"); }},
    { title: '{{_("Go to Sent")|escapejs}}',          keys: "g s",     callback: function(e) { Mailpile.go("/in/sent/"); }},
    { title: '{{_("Go to Spam")|escapejs}}',          keys: "g j",     callback: function(e) { Mailpile.go("/in/spam/"); }},
    { title: '{{_("Go to Trash")|escapejs}}',         keys: "g t",     callback: function(e) { Mailpile.go("/in/trash/"); }},
    { title: '{{_("Follow search hint")|escapejs}}',  keys: "g h",     callback: function(e) { Mailpile.go($('.bulk-actions-hints a').eq(0).attr('href')); }},
    { title: '{{_("Reply to e-mail")|escapejs}}',     keys: "r",       callback: function(e) { Mailpile.keybinding_reply(); }},
    { title: '{{_("Reply to many e-mails at once")|escapejs}}',
                                                      keys: "shift+r", callback: function(e) { Mailpile.keybinding_reply('many'); }},
    { title: '{{_("Forward one or more e-mails")|escapejs}}',
                                                      keys: "shift+f", callback: function(e) { Mailpile.keybinding_forward(); }},
    { title: '{{_("Mark as read")|escapejs}}',        keys: "shift+i", callback: function(e) { Mailpile.keybinding_mark_read(); }},
    { title: '{{_("Mark as unread")|escapejs}}',      keys: "shift+u", callback: function(e) { Mailpile.keybinding_mark_unread(); }},
    { title: '{{_("Move to spam")|escapejs}}',        keys: "!",       callback: function(e) { Mailpile.keybinding_move_messages('spam'); }},
    { title: '{{_("Archive e-mail")|escapejs}}',      keys: "e",       callback: function(e) { Mailpile.keybinding_move_messages('!archive'); }},
    { title: '{{_("Untag, remove e-mail from view")|escapejs}}',
                                                      keys: "shift+e", callback: function(e) { Mailpile.keybinding_move_messages('!untag', 'keep_new'); }},
    { title: '{{_("Delete e-mail")|escapejs}}',       keys: "#",       callback: function(e) { Mailpile.keybinding_move_messages('trash'); }},
    { title: '{{_("Undo last action")|escapejs}}',    keys: "z",       callback: function(e) { Mailpile.keybinding_undo_last(); }},
    { title: '{{_("Select all visible")|escapejs}}',  keys: "* a",     callback: function(e) { Mailpile.bulk_action_select_all(); }},
    { title: '{{_("Select all matching search")|escapejs}}',
                                                      keys: "* s",     callback: function(e) { Mailpile.keybinding_select_all_matches(); }},
    { title: '{{_("Deselect all")|escapejs}}',        keys: "* n",     callback: function(e) { Mailpile.bulk_action_select_none(); }},
    { title: '{{_("Dismiss all notifications")|escapejs}}',
                                                      keys: "_",       callback: function(e) { $('a.notifications-close-all').eq(0).trigger('click'); }},
    { title: '{{_("Account List")|escapejs}}',        keys: "g a",     callback: function(e) { Mailpile.go("/profiles/"); }},
    { title: '{{_("Security and Privacy Settings")|escapejs}}',
                                                      keys: "g p",     callback: function(e) { Mailpile.go("/settings/privacy.html"); }},
    // Assign hot-keys to the contextual actions (Edit, New, Attachments, ...)
    {                                                 keys: "1",       callback: function(e) { $('#content-tools a').not('.hide').eq(0).trigger('click'); }},
    {                                                 keys: "2",       callback: function(e) { $('#content-tools a').not('.hide').eq(1).trigger('click'); }},
    {                                                 keys: "3",       callback: function(e) { $('#content-tools a').not('.hide').eq(2).trigger('click'); }},
    {                                                 keys: "4",       callback: function(e) { $('#content-tools a').not('.hide').eq(3).trigger('click'); }},
    {                                                 keys: "5",       callback: function(e) { $('#content-tools a').not('.hide').eq(4).trigger('click'); }},
    {                                                 keys: "6",       callback: function(e) { $('#content-tools a').not('.hide').eq(5).trigger('click'); }},
    {                                                 keys: "7",       callback: function(e) { $('#content-tools a').not('.hide').eq(6).trigger('click'); }},
    {                                                 keys: "8",       callback: function(e) { $('#content-tools a').not('.hide').eq(7).trigger('click'); }},
    {                                                 keys: "9",       callback: function(e) { $('#content-tools a').not('.hide').eq(8).trigger('click'); }},
    // Assign hot-keys to the contextual bulk actions (toggle read/...)
    {                                                 keys: "* 1",       callback: function(e) { $('.bulk-actions ul a').not('.hide').eq(0).trigger('click'); }},
    {                                                 keys: "* 2",       callback: function(e) { $('.bulk-actions ul a').not('.hide').eq(1).trigger('click'); }},
    {                                                 keys: "* 3",       callback: function(e) { $('.bulk-actions ul a').not('.hide').eq(2).trigger('click'); }},
    {                                                 keys: "* 4",       callback: function(e) { $('.bulk-actions ul a').not('.hide').eq(3).trigger('click'); }},
    {                                                 keys: "* 5",       callback: function(e) { $('.bulk-actions ul a').not('.hide').eq(4).trigger('click'); }},
    {                                                 keys: "* 6",       callback: function(e) { $('.bulk-actions ul a').not('.hide').eq(5).trigger('click'); }},
    {                                                 keys: "* 7",       callback: function(e) { $('.bulk-actions ul a').not('.hide').eq(6).trigger('click'); }},
    {                                                 keys: "* 8",       callback: function(e) { $('.bulk-actions ul a').not('.hide').eq(7).trigger('click'); }},
    {                                                 keys: "* 9",       callback: function(e) { $('.bulk-actions ul a').not('.hide').eq(8).trigger('click'); }},
    // Assign hot-keys to the visible user-generated tags...
    {                                                 keys: "g 1",     callback: function(e) { $('#sidebar-lists #sidebar-tag li').not('.hide').find('a.sidebar-tag').eq(0).trigger('click'); }},
    {                                                 keys: "g 2",     callback: function(e) { $('#sidebar-lists #sidebar-tag li').not('.hide').find('a.sidebar-tag').eq(1).trigger('click'); }},
    {                                                 keys: "g 3",     callback: function(e) { $('#sidebar-lists #sidebar-tag li').not('.hide').find('a.sidebar-tag').eq(2).trigger('click'); }},
    {                                                 keys: "g 4",     callback: function(e) { $('#sidebar-lists #sidebar-tag li').not('.hide').find('a.sidebar-tag').eq(3).trigger('click'); }},
    {                                                 keys: "g 5",     callback: function(e) { $('#sidebar-lists #sidebar-tag li').not('.hide').find('a.sidebar-tag').eq(4).trigger('click'); }},
    {                                                 keys: "g 6",     callback: function(e) { $('#sidebar-lists #sidebar-tag li').not('.hide').find('a.sidebar-tag').eq(5).trigger('click'); }},
    {                                                 keys: "g 7",     callback: function(e) { $('#sidebar-lists #sidebar-tag li').not('.hide').find('a.sidebar-tag').eq(6).trigger('click'); }},
    {                                                 keys: "g 8",     callback: function(e) { $('#sidebar-lists #sidebar-tag li').not('.hide').find('a.sidebar-tag').eq(7).trigger('click'); }},
    {                                                 keys: "g 9",     callback: function(e) { $('#sidebar-lists #sidebar-tag li').not('.hide').find('a.sidebar-tag').eq(8).trigger('click'); }},
    {
      keys: "t",
      callback: function(e) { Mailpile.Terminal.toggle("small"); return false; },
      title: "{{_("Show terminal (small).")|escapejs}}"
    }
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
  local_storage: localStorage || {},
  unsafe_template: function(tpl) { return _.template(tpl); },
  safe_template: function(tpl) {
    return _.template(tpl, undefined, {
      evaluate: /<%([\s\S]+?)%>/g,
      // interpolate: /<%=([\s\S]+?)%>/g, <- DISABLED FOR SAFETY :)
      escape: /<%[-=]([\s\S]+?)%>/g
    });
  },
  safe_jinjaish_template: function(tpl) {
    return _.template(tpl, undefined, {
      evaluate: /[{]%([\s\S]+?)%[}]/g,
      // interpolate: /<%=([\s\S]+?)%>/g, <- DISABLED FOR SAFETY :)
      escape: /{[{]([\s\S]+?)[}]}/g
    });
  }
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
    if (status == "user") advice = "";
    if (fullscreen) {
      if (!$('#connection-down').length) {
        var template = Mailpile.safe_template($('#template-connection-down').html());
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
      if (command != '/0/cached/' && command != '/0/logs/events/') {
        Mailpile.notification({
          status: 'error',
          message: '{{_("Oops. Mailpile failed to complete your task.")|escapejs}}',
          icon: 'icon-signature-unknown'
        });
      }
      Mailpile.API._ajax_dead_count = 0;
      return;
    }
    if (response.status == 0 ||    // Some internal error state
        response.status == 503 ||  // PageKite or reverse proxy down
        status == 'parsererror' || // Server replaced with sth. else?
        response.status == 302) {  // Server gone somewhere else?
      // Tell the user to check the network, but could probably provide clearer
      // feedback.
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
          if (response.result) {
            Mailpile.API._ajax_is_alive();
            if (callback) return callback(response, status);
          }
          else {
            Mailpile.API._ajax_error(base_url, command, data,
                                     method, response, status);
            if (error_callback) error_callback(response, status);
          }
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
          if (callback) return callback(response, status);
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

  with_template: function(name, action, error, flags, unsafe) {
      var url = "{{ config.sys.http_path }}/jsapi/templates/" + name + ".html";
      if (flags) {
        url += '?ui_flags=' + flags.replace(' ', '+');
      }
      $.ajax({
        url: url,
        type: 'GET',
        success: function(data) {
          action((unsafe) ? Mailpile.unsafe_template(data)
                          : Mailpile.safe_template(data));
        },
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
{% include("jsapi/ui/terminal.js") %}


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
