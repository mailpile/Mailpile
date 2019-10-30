Mailpile.Terminal = {
    settings: {
        prompt: 'mailpile>',
        enabled: false,
        fullscreen: false,
        session: null,
    }
};

Mailpile.Terminal.atBottom = function() {
    var d = document.getElementById("terminal_output");
    return (d.scrollHeight - d.scrollTop === d.clientHeight);
};

Mailpile.Terminal.scrollDown = function() {
    var d = document.getElementById("terminal_output");
    d.scrollTop = d.scrollHeight;
    $("#terminal_input input").focus();
};

Mailpile.Terminal.updateDebugLog = function(new_lines) {
    if (!new_lines || !new_lines.length) return;
    var wasAtBottom = Mailpile.Terminal.atBottom();
    for (i in new_lines) {
        var log_line_id = new_lines[i][0];
        var log_ts = Math.floor(new_lines[i][1] * 1000);
        var log_time = (new Date(log_ts)).toLocaleTimeString();
        var log_msg = new_lines[i][2].replace(/&/g, '&amp;')
                                     .replace(/>/g, '&gt;')
                                     .replace(/</g, '&lt;');
        var $existing = $('#log_line_' + log_line_id);
        if ($existing.length) {
            $existing.find('.ts').html(log_time);
            $existing.find('.log').html(log_msg);
        }
        else {
            $("#terminal_output").append(
                '<div data-ts="'+ log_ts +'" id="log_line_'+ log_line_id +'" class="log">'+
                  '[<span class="ts">'+ log_time +'</span>] '+
                  '<span class="log">'+ log_msg +'</span>'+
                '</div>');
        }
    }
    if (wasAtBottom) {
        var $terminal = $("#terminal_output");
        var $elements = $terminal.children("div");
        $elements.sort(function(a, b) {
            a = a.getAttribute('data-ts');
            b = b.getAttribute('data-ts');
            if (a < b) return -1;
            if (a > b) return 1;
            return 0;
        });
        $elements.detach();
        $elements = $elements.slice(-500);
        $elements.appendTo($terminal);
        Mailpile.Terminal.scrollDown();
    }
};

Mailpile.Terminal.output = function(mode_out) {
    // We're going to inject new elements timestamped 2 seconds in the future,
    // to make any debug log lines sort *above* the new output for a short
    // period of time, so they're less disruptive.
    var elem_ts = (new Date().getTime()) + 2000;
    var $output = $('<div data-ts="'+elem_ts+'">').addClass("output");

    if (mode_out[0] == "html") {
        // FIXME: The HTML mode will need a fair bit of CSS to work well.
        var $new_elem = $(mode_out[1]);
        $new_elem.find('div.footer-nav').remove();
        $output.addClass('html_blob')
               .addClass('sub-content')
               .addClass('sub-content-view').append($new_elem);
    }
    else {
        $output.html(mode_out[1].replace(/&/g, '&amp;')
                                .replace(/>/g, '&gt;')
                                .replace(/</g, '&lt;'));
    }
    $("#terminal_output").append($output);
    Mailpile.Terminal.scrollDown();
};

Mailpile.Terminal.handleResponse = function(r) {
    if (r.status == "success") {
        if (r.result.result.error) {
            Mailpile.Terminal.output(["text", "Error: " + r.result.result.error]);
        } else {
            Mailpile.Terminal.output(r.result.result);
        }
    } else if (r.status == "error") {
        Mailpile.Terminal.output(["text", r.message]);
    }
}

Mailpile.Terminal.submitCommand = function(ev) {
    Mailpile.Terminal.executeCommand($("#terminal_input input").val());
    return false;
};

Mailpile.Terminal.executeCommand = function(cmd) {
    $("#terminal_input input").val("");
    if (cmd == "/full") return Mailpile.Terminal.makeFull();
    if (cmd == "/small") return Mailpile.Terminal.makeSmall();
    if (cmd == "/clear") return Mailpile.Terminal.clearOutput();
    if (cmd == "/close") return Mailpile.Terminal.session_end();
    if (!cmd) return Mailpile.Terminal.executeCommand('help/splash web_terminal');
    var chars = 10 * $('#terminal #console').width() / $('#terminal #prompt').width();
    Mailpile.Terminal.output(["text", "mailpile> " + cmd]);
    Mailpile.API.terminal_command_post({
            command: cmd,
            width: chars,
            sid: Mailpile.Terminal.settings.session},
        Mailpile.Terminal.handleResponse);
};

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
    "        <span id=\"prompt\">mailpile&gt; </span>" +
    "        <form>" +
    "            <input>" +
    "        </form>" +
    "    </div>" +
    "  </div>" +
    "  <div id=\"debug_container\">" +
    "     <div id=\"debug_output\"></div>" +
    "  </div>" +
    "</div>");
    $("#terminal_input form")
        .submit(Mailpile.Terminal.submitCommand)
        .find('input').on('keydown', function(ev, input) {
            var code = ev.charCode || ev.keyCode;
            if (code == 27) {  // ESC
                Mailpile.Terminal.toggle();
                ev.preventDefault();
                return false;
            }
            if (code == 9) {  // TAB
                // FIXME: Command completion, please
                ev.preventDefault();
                return false;
            }
            // History on keyup/keydown, please!
        });
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
        $("body").focus();
    } else {
        if (size == "full") {
            $("#terminal").css("height", "100%");
        } else {
            $("#terminal").css("height", "400px");
        }
        $("#terminal_blanket").show();
        $("#terminal").slideDown('fast');
        Mailpile.Terminal.settings.enabled = true;
    }
    Mailpile.Terminal.scrollDown();
};

Mailpile.Terminal.makeFull = function() {
    $("#terminal").animate({"height": "100%"}, Mailpile.Terminal.scrollDown);
    $("#terminal_fullsize_button").hide();
    $("#terminal_halfsize_button").show();
}

Mailpile.Terminal.makeSmall = function() {
    $("#terminal").animate({"height": "400px"}, Mailpile.Terminal.scrollDown);
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
        Mailpile.Terminal.executeCommand('help/splash web_terminal');
        Mailpile.Terminal.scrollDown();
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
