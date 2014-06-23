Mailpile.focus_search = function() {
    $("#search-query").focus(); return false;
};


/* Search - Action Select */
Mailpile.pile_action_select = function(item) {
    // Add To Data Model
    Mailpile.bulk_cache_add('messages_cache', item.data('mid'));

    // Update Bulk UI
    Mailpile.bulk_actions_update_ui();

    // Style & Select Checkbox
    item.removeClass('result').addClass('result-on')
        .data('state', 'selected')
        .find('td.checkbox input[type=checkbox]')
        .val('selected')
        .prop('checked', true);
};


/* Search - Action Unselect */
Mailpile.pile_action_unselect = function(item) {
    // Remove From Data Model
    Mailpile.bulk_cache_remove('messages_cache', item.data('mid'));

    // Hide Actions
    Mailpile.bulk_actions_update_ui();

    // Style & Unselect Checkbox
    item.removeClass('result-on').addClass('result')
        .data('state', 'normal')
        .find('td.checkbox input[type=checkbox]')
        .val('normal')
        .prop('checked', false);
};


/* Search - Result List */
Mailpile.results_list = function() {
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


Mailpile.update_search = function(ev) {
    $("#pile-newmessages-notification").slideUp("slow");
    console.log("Refreshing ", Mailpile.instance);
    url = "/api/0/search/as.jhtml?" + $.param(Mailpile.instance.state.query_args);
    $.getJSON(url, {}, function(data) {
        if (data.status == "success") {
            $("#content-view").html(data.result);
        }
        console.log(data);
    });
};

$().ready(function() {
    $("#pile-newmessages-notification").click(Mailpile.update_search);
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

            if (Notification.permission == "granted") {
                new Notification(
                    ev.data.messages + "{{_(' new messages received')}}", 
                    { 
                        body:'{{_("Your pile is growing...")}}',
                        icon:'/static/img/logo-color.png', 
                    }  
                )
            }
        }
    });
});
