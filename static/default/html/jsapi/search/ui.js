MailPile.prototype.focus_search = function() {
    $("#search-query").focus(); return false;
};


/* Search - Action Select */
MailPile.prototype.pile_action_select = function(item) {
    // Add To Data Model
    mailpile.bulk_cache_add('messages_cache', item.data('mid'));

    // Update Bulk UI
    mailpile.bulk_actions_update_ui();

    // Style & Select Checkbox
    item.removeClass('result').addClass('result-on')
        .data('state', 'selected')
        .find('td.checkbox input[type=checkbox]')
        .val('selected')
        .prop('checked', true);
};


/* Search - Action Unselect */
MailPile.prototype.pile_action_unselect = function(item) {
    // Remove From Data Model
    mailpile.bulk_cache_remove('messages_cache', item.data('mid'));

    // Hide Actions
    mailpile.bulk_actions_update_ui();

    // Style & Unselect Checkbox
    item.removeClass('result-on').addClass('result')
        .data('state', 'normal')
        .find('td.checkbox input[type=checkbox]')
        .val('normal')
        .prop('checked', false);
};


/* Search - Result List */
MailPile.prototype.results_list = function() {
    // Navigation
    $('#btn-display-list').addClass('navigation-on');
    $('#btn-display-graph').removeClass('navigation-on');
    
    // Show & Hide View
    $('#pile-graph').hide('fast', function() {
        $('#form-pile-results').show('normal');
        $('#pile-results').show('fast');
        $('.pile-speed').show('normal');
        $('#footer').show('normal');
    });
};


MailPile.prototype.update_search = function(ev) {
    $("#pile-newmessages-notification").slideUp("slow");
    console.log("Refreshing ", mailpile.instance);
    url = "/api/0/search/as.jhtml?" + $.param(mailpile.instance.state.query_args);
    $.getJSON(url, {}, function(data) {
        if (data.status == "success") {
            $("#content-view").html(data.result);
        }
        console.log(data);
    });
};

$().ready(function() {
    $("#pile-newmessages-notification").click(mailpile.update_search);
    EventLog.subscribe(".commands.Rescan", function(ev) {
        if (ev.flags.indexOf("R") != -1) {
            console.log("Started rescanning...");
            $("#topbar-logo-bluemail").fadeOut(2000);
            $("#topbar-logo-redmail").hide(2000);
            $("#topbar-logo-greenmail").hide(3000);
            $("#topbar-logo-bluemail").fadeIn(2000);
            $("#topbar-logo-greenmail").fadeIn(4000);
            $("#topbar-logo-redmail").fadeIn(6000);
        }
        if (ev.flags.indexOf("c") != -1 && ev.data.messages > 0) {
            $("#pile-newmessages-notification").slideDown("slow");

            if (window.webkitNotifications.checkPermission() == 0) {
                window.webkitNotifications.createNotification(
                    '/static/img/logo-color.png', 
                    ev.data.messages + "{{_(' new messages received')}}", 
                    '{{_("Your pile is growing...")}}').show();
            }
        }
    });
});
