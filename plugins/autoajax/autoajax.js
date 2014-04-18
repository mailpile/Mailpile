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

var update_using_jhtml = function(original_url) {
    return $.ajax({
        url: jhtml_url(original_url),
        type: 'GET',
        dataType: 'json',
        success: function(data) {
            $('#content-view').html(data['results']);
        }
    });
};

$(document).ready(function(){
    if (mailpile && mailpile.instance &&
            mailpile.instance['command'] == 'search') {
        $('a').each(function(idx, elem) {
            var url = $(elem).attr('href');
            if (url && ((url.indexOf('/in/') == 0) ||
                        (url.indexOf('/search/') == 0))) {
                $(elem).click(function(ev) {
                    if (update_using_jhtml(url)) ev.preventDefault();
                });
            }
        });
    }
});

return {
    'update_using_jhtml': update_using_jhtml
}
