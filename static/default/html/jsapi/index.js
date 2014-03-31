
var MailpileAPI = (function() {
    var api = {
        {%- for command in result %}
        {{command.url|replace("/", "_")}}: "/api/0/{{command.url}}/",
        {%- endfor -%}
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
        {% for command in result %}
        {{command.url|replace("/", "_")}}: function(
            {%- for key in command.query_vars -%}pv_{{key|replace("@", "")}}, {% endfor -%}
            {%- for key in command.post_vars -%}pv_{{key|replace("@", "")|replace(".","_")|replace("-","_")}}, {% endfor -%}
            callback) {
            return action(api.{{command.url|replace("/", "_")}}, {
                {%- for key in command.query_vars %}
                    "{{key}}": pv_{{key|replace("@", "")}},{%- endfor %}
                {%- for key in command.post_vars %}
                    "{{key}}": pv_{{key|replace("@", "")}},{%- endfor %}
            }, "{{command.method}}", callback);
        },
        {%- endfor %}
    }
})();
