/*
 * This code seamlessly upgrades any <a href=...> which would cause a search
 * to happen, to instead trigger an AJAX load.  This should make searches
 * feel almost instantaneous, while allowing us to keep all the template
 * logic in the back-end as Jinja2.
 *
 * FIXME:
 *   - Invoke any logic pertaining to display modes before updating
 *   - Use pushstate to update the browser history and location bar
 */

var update_using_jhtml;
var prepare_new_content;

prepare_new_content = function(selector) {
    $(selector).find('a').each(function(idx, elem) {
        var url = $(elem).attr('href');
        // FIXME: Should we add some majick to avoid dup click handlers?
        if (url && ((url.indexOf('/in/') == 0) ||
                    (url.indexOf('/browse/') == 0) ||
                    (url.indexOf('/search/') == 0))) {
            $(elem).click(function(ev) {
                if (update_using_jhtml(url)) ev.preventDefault();
            });
        }
    });
};

update_using_jhtml = function(original_url) {
    if ((Mailpile.instance['command'] == 'search') ||
            (Mailpile.instance['command'] == 'ls')) {
        var cv = $('#content-view');
        cv.hide();
        return $.ajax({
            url: Mailpile.API.jhtml_url(original_url),
            type: 'GET',
            success: function(data) {
                cv.html(data['result']).show();
                prepare_new_content(cv);

                // FIXME: The back button is still broken
                history.pushState(null, data['message'], original_url);
                Mailpile.messages_cache = [];
            }
        });
    }
    else {
        return false;
    }
};

$(document).ready(function(){
    if (Mailpile && Mailpile.instance) {
        prepare_new_content('body');
    }
    EventLog.subscribe('.command_cache.CommandCache', function(ev) {
        for (var cidx in ev.data.cache_ids) {
            var cid = ev.data.cache_ids[cidx];
            var $inpage = $('.content-'+cid);
            if ($inpage.length > 0) {
                Mailpile.API.cached_get({
                    id: cid,
                    _output: Mailpile.API.jhtml_url($inpage.data('template')
                                                    || 'as.html')
                }, function(json) {
                    var cid = json.state.cache_id;
                    $('.content-'+cid).replaceWith(json.result);
                    prepare_new_content($('.content-'+cid));
                });
            }
        }
    });
});

return {
    'update_using_jhtml': update_using_jhtml,
    'prepare_new_content': prepare_new_content
}
