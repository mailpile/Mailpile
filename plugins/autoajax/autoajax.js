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
var jhtml_url = function(original_url) {
    var new_url = original_url;
    var html = new_url.indexOf('.html');
    if (html != -1) {
        new_url = (new_url.slice(0, html+1) + 'j' +
                   new_url.slice(html+1));
    }
    else {
        var qs = new_url.indexOf('?');
        if (qs != -1) {
            new_url = (new_url.slice(0, qs) + 'as.jhtml' +
                       new_url.slice(qs));
        }
        else {
            var anch = new_url.indexOf('#');
            if (anch != -1) {
                new_url = (new_url.slice(0, anch) + 'as.jhtml' +
                           new_url.slice(anch));
            }
            else {
                new_url += 'as.jhtml';
            }
        }
    }
    return new_url;
};

prepare_new_content = function(selector) {
    $(selector).find('a').each(function(idx, elem) {
        var url = $(elem).attr('href');
        if (url && ((url.indexOf('/in/') == 0) ||
                    (url.indexOf('/search/') == 0))) {
            $(elem).click(function(ev) {
                if (update_using_jhtml(url)) ev.preventDefault();
            });
        }
    });
};

update_using_jhtml = function(original_url) {
    if (Mailpile.instance['command'] == 'search') {
        var cv = $('#content-view');
        cv.hide();
        return $.ajax({
            url: jhtml_url(original_url),
            type: 'GET',
            success: function(data) {
                cv.html(data['result']).fadeIn('fast');
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
});

return {
    'update_using_jhtml': update_using_jhtml,
    'prepare_new_content': prepare_new_content
}
