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
    api: {}
};


/* AJAXy wrappers for the Mailpile API */
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
