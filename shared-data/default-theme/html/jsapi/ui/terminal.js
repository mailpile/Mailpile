

Mailpile.Terminal = {
    settings: {
        prompt: 'mailpile>',
        enabled: false,
        fullscreen: false,
        session: null,
    }
};

Mailpile.Terminal.output = function(out) {
    if (typeof(out) === 'object' || typeof(out) === 'array') {
        out = JSON.stringify(out);
    }
    var s =  out.replace(/&/g, '&amp;')
                .replace(/>/g, '&gt;')
                .replace(/</g, '&lt;')
                .replace(/"/g, '&quot;');
    $("#terminal_output").append("<div class=\"output\">" + s + "</div>");
    var d = document.getElementById("terminal_output");
    d.scrollTop = d.scrollHeight;
}

Mailpile.Terminal.handleResponse = function(r) {
    if (r.status == "success") {
        Mailpile.Terminal.output(r.result.result);
    } else if (r.status == "error") {
        Mailpile.Terminal.output(r.message);
    }
}

Mailpile.Terminal.executeCommand = function() {
    var cmd = $("#terminal_input input").val();
    $("#terminal_input input").val("");
    Mailpile.Terminal.output("mailpile> " + cmd);
    if (cmd == "exit") {
        Mailpile.Terminal.session_end();
    } else {
        Mailpile.API.terminal_command_post(
            {command: cmd, sid: Mailpile.Terminal.settings.session},
            Mailpile.Terminal.handleResponse);
    }
    return false;
}

Mailpile.Terminal.init = function() {
    $("body").append("<div id=\"terminal\">" +
    "    <div id=\"terminal_output\"></div>" +
    "    <div id=\"terminal_input\">mailpile&gt; " +
    "        <form>" +
    "            <input>" +
    "        </form>" +
    "   </div>" +
    "</div>");
    $("#terminal_input form").submit(Mailpile.Terminal.executeCommand);
}

Mailpile.Terminal.toggle = function(size) {
    if (!Mailpile.Terminal.settings.session) {
        Mailpile.Terminal.session_start();
    }
    if (Mailpile.Terminal.settings.enabled) {
        Mailpile.Terminal.settings.enabled = false;
        $("#terminal_input input").blur();
        $("#terminal").slideToggle('fast');
    } else {
        if (size == "full") {
            $("#terminal").css("height", "100%");
        } else if (size == "small") {
            $("#terminal").css("height", "350px");
        }
        $("#terminal").slideToggle('fast');
        Mailpile.Terminal.settings.enabled = true;
        $("#terminal_input input").focus();
    }
    var d = document.getElementById("terminal_output");
    d.scrollTop = d.scrollHeight;
};

Mailpile.Terminal.hide = function() {
    $("#terminal").slideUp('fast');
    Mailpile.Terminal.settings.enabled = false;
    $("#terminal_input input").blur();
};

Mailpile.Terminal.session_start = function() {
    Mailpile.API.terminal_session_new_post({}, function(data) {
        console.log(data);
        console.log("Session started");
        Mailpile.Terminal.settings.session = data.result.sid;
    });
};

Mailpile.Terminal.session_end = function() {
    Mailpile.API.terminal_session_end_post(
        {sid: Mailpile.Terminal.settings.session},
        function(data) {
            Mailpile.Terminal.settings.session = null;
            Mailpile.Terminal.hide();
        }
    );
};

$(function() {
    Mailpile.Terminal.init();
})
