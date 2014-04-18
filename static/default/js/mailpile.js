/*jslint browser:true, nomen:true */
/*globals $, alert, _, Mousetrap, Favico */
// Make console.log not crash JS browsers that don't support it
if (!window.console) {
    window.console = { log: $.noop, group: $.noop, groupEnd: $.noop, info: $.noop, error: $.noop };
}

var mailpile,
    favicon;


function MailPile() {
    "use strict";
    this.instance       = {};
    this.search_cache   = [];
    this.messages_cache = [];
    this.tags_cache     = [];
    this.contacts_cache = [];
    this.keybindings    = [
        ["normal", "/",         function () { $("#search-query").focus(); return false; }],
        ["normal", "c",         function () { mailpile.compose(); }],
        ["normal", "g i",       function () { mailpile.go("/in/inbox/"); }],
        ["normal", "g d",       function () { mailpile.go("/in/drafts/"); }],
        ["normal", "g c",       function () { mailpile.go("/contact/list/"); }],
        ["normal", "g n c",     function () { mailpile.go("/contact/add/"); }],
        ["normal", "g t",       function () { mailpile.go("/tag/list/"); }],
        ["normal", "g n t",     function () { mailpile.go("/tag/add/"); }],
        ["normal", "g s",       function () { mailpile.go("/settings/profiles/"); }],
        ["normal", "command+z", function () { alert('Undo Something '); }],
        ["normal", ["s"],       function () { mailpile.keybinding_move_message('spam'); }],
        ["normal", ["d"],       function () { mailpile.keybinding_move_message('trash'); }],
        ["normal", ["t"],       function () { mailpile.render_modal_tags(); }],
        ["global", "esc",       function () {
            $('input[type=text]').blur();
            $('textarea').blur();
        }]
    ];
    this.commands       = [];
    this.graphselected  = [];
    this.defaults       = {
        view_size: "comfy"
    };
    this.api = {
        compose      : "/api/0/message/compose/",
        compose_send : "/api/0/message/update/send/",
        compose_save : "/api/0/message/update/",
        contacts     : "/api/0/search/address/",
        message      : "/api/0/message/=",
        tag          : "/api/0/tag/",
        tag_list     : "/api/0/tag/list/",
        tag_add      : "/api/0/tag/add/",
        search_new   : "/api/0/search/?q=in%3Anew",
        search       : "/api/0/search/",
        settings_add : "/api/0/settings/add/"
    };
    this.urls = {
        message_draft : "/message/draft/=",
        message_sent  : "/thread/="
    };
    this.plugins = [];
}

MailPile.prototype.go = function (url) {
    "use strict";
    window.location.href = url;
};

MailPile.prototype.bulk_cache_add = function (type, value) {
    "use strict";
    if (_.indexOf(this[type], value) < 0) {
        this[type].push(value);
    }
};

MailPile.prototype.bulk_cache_remove = function (type, value) {
    "use strict";
    if (_.indexOf(this[type], value) > -1) {
        this[type] = _.without(this[type], value);
    }
};

MailPile.prototype.show_bulk_actions = function (elements) {
    "use strict";
    $.each(elements, function () {
        $(this).css('visibility', 'visible');
    });
};

MailPile.prototype.hide_bulk_actions = function (elements) {
    "use strict";
    $.each(elements, function () {
        $(this).css('visibility', 'hidden');
    });
};

MailPile.prototype.get_new_messages = function (actions) {
    "use strict";
    $.ajax({
        url         : mailpile.api.search_new,
        type        : 'GET',
        dataType    : 'json',
        success     : function (response) {
            if (response.status === 'success') {
                actions(response);
            }
        }
    });
};

MailPile.prototype.render = function () {
    "use strict";

    // Dynamic CSS Reiszing
    var item,
        keybinding;

    function dynamic_sizing() {
        var content_width,
            content_height,
            content_tools_height,
            fix_content_view_height,
            new_content_width,
            sidebar_width,
            sidebar_height = $('#sidebar').height();

        // Is Tablet or Mobile
        if ($(window).width() < 1024) {
            sidebar_width = 0;
        } else {
            sidebar_width = 225;
        }

        content_width  = $(window).width() - sidebar_width;
        // DPO: content_height is defined here, but doesn't seem to be used.
        content_height = $(window).height() - 62;
        content_tools_height = $('#content-tools').height();
        fix_content_view_height = sidebar_height - content_tools_height;
        new_content_width = $(window).width() - sidebar_width;

        $('#content-tools').css('position', 'fixed');
        $('.sub-navigation').width(content_width);
        $('#thread-title').width(content_width);

        // Set Content View
        $('#content-tools, .sub-navigation, .bulk-actions').width(new_content_width);
        $('#content-view').css({'height': fix_content_view_height, 'top': content_tools_height});
    }

    dynamic_sizing();

    // Resize Elements on Drag
    window.onresize = function (event) {
        // DPO: event is defined here, but doesn't seem to be used.
        dynamic_sizing();
    };

    // Show Mailboxes
    if ($('#sidebar-tag-outbox').find('span.sidebar-notification').html() !== undefined) {
        $('#sidebar-tag-outbox').show();
    }

    // Mousetrap Keybindings
    for (item in mailpile.keybindings) {
        if (mailpile.keybindings.hasOwnProperty(item)) {
            keybinding = mailpile.keybindings[item];
            if (keybinding[0] === "global") {
                Mousetrap.bindGlobal(keybinding[1], keybinding[2]);
            } else {
                Mousetrap.bind(keybinding[1], keybinding[2]);
            }
        }
    }

};

MailPile.prototype.command = function (command, data, method, callback) {
    // DPO: data is defined here, but doesn't seem to be used.
    "use strict";
    if (method !== "GET" && method !== "POST") {
        method = "GET";
    }
    $.ajax({
        url      : command,
        type     : method,
        dataType : 'json',
        success  : callback
    });
};

mailpile = new MailPile();
favicon = new Favico({animation: 'popFade'});

// Non-exposed functions: www, setup
$(document).ready(function () {
    "use strict";
    // Render
    mailpile.render();
});


