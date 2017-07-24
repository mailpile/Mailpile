

Mailpile.Terminal = {
    settings: {
        prompt: 'mailpile>',
        enabled: false,
        fullscreen: false,
        session: null,
    }
};

Mailpile.Terminal.debugOutput = function(out) {
    if (typeof(out) === 'object' || typeof(out) === 'array') {
        out = JSON.stringify(out);
    }
    var s =  out.replace(/&/g, '&amp;')
                .replace(/>/g, '&gt;')
                .replace(/</g, '&lt;')
                .replace(/"/g, '&quot;');
    $("#terminal_output").append("<div class=\"output\">" + s + "</div>");
    var d = document.getElementById("debug_output");
    d.scrollTop = d.scrollHeight;
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
};

Mailpile.Terminal.handleResponse = function(r) {
    if (r.status == "success") {
        if (r.result.result.error) {
            Mailpile.Terminal.output("Error: " + r.result.result.error);
        } else {
            Mailpile.Terminal.output(r.result.result);
        }
    } else if (r.status == "error") {
        Mailpile.Terminal.output(r.message);
    }
}

Mailpile.Terminal.executeCommand = function() {
    var cmd = $("#terminal_input input").val();
    $("#terminal_input input").val("");
    Mailpile.Terminal.output("mailpile> " + cmd);
    if (cmd == "/exit") {
        Mailpile.Terminal.session_end();
    } else if (cmd == "/clear") {
        Mailpile.Terminal.clearOutput();
    } else if (cmd == "") {
        // Do nothing.
    } else {
        Mailpile.API.terminal_command_post(
            {command: cmd, sid: Mailpile.Terminal.settings.session},
            Mailpile.Terminal.handleResponse);
    }
    return false;
}

Mailpile.Terminal.init = function() {
    $("body").append(
    "<div id=\"terminal_blanket\" onclick=\"Mailpile.Terminal.hide();\">" +
    "</div>" +
    "<div id=\"terminal\">" +
    "  <div id=\"console\">" +
    "    <div id=\"terminal_output\"></div>" +
    "    <div id=\"terminal_input\">" +
    "        <a onclick=\"Mailpile.Terminal.session_end();\">" +
    "            <span class=\"icon icon-x\">" +
    "        </a>" +
    "        <a id=\"terminal_fullsize_button\" onclick=\"Mailpile.Terminal.makeFull();\">" +
    "            <span class=\"icon icon-arrow-down\">" +
    "        </a>" +
    "        <a id=\"terminal_halfsize_button\" onclick=\"Mailpile.Terminal.makeSmall();\">" +
    "            <span class=\"icon icon-arrow-up\">" +
    "        </a>" +
    "        mailpile&gt; " +
    "        <form>" +
    "            <input>" +
    "        </form>" +
    "    </div>" +
    "  </div>" +
    // For now we're disabling the debug window for now because it's incomplete.
    // TODO: Bring this to life! -- @smari 2017-07-24
    // "  <div id=\"debug_container\">" +
    // "     <div id=\"debug_output\"></div>" +
    // "  </div>" +
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
        $("#terminal_blanket").show();
        $("#terminal").slideUp('fast');
    } else {
        if (size == "full") {
            $("#terminal").css("height", "100%");
        } else if (size == "small") {
        }
        $("#terminal").css("height", "350px");
        $("#terminal_blanket").show();
        $("#terminal").slideDown('fast');
        Mailpile.Terminal.settings.enabled = true;
        $("#terminal_input input").focus();
    }
    var d = document.getElementById("terminal_output");
    d.scrollTop = d.scrollHeight;
};

Mailpile.Terminal.makeFull = function() {
    $("#terminal").animate({"height": "100%"});
    $("#terminal_fullsize_button").hide();
    $("#terminal_halfsize_button").show();
}

Mailpile.Terminal.makeSmall = function() {
    $("#terminal").animate({"height": "350px"});
    $("#terminal_halfsize_button").hide();
    $("#terminal_fullsize_button").show();
}

Mailpile.Terminal.hide = function() {
    $("#terminal_blanket").hide();
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
            setTimeout(Mailpile.Terminal.clearOutput, 500);
        }
    );
};

Mailpile.Terminal.clearOutput = function() {
    $("#terminal_output").empty();
};

$(function() {
    Mailpile.Terminal.init();
})
