/* MailDeck.js is the javascript code
   The name of the returned class will be `mailpile.plugins.maildeck`.
 */
return {
    activity_click: function(e) {
        e.preventDefault();
      
        $('#sidebar').hide();
      
        new_mailpile.plugins.maildeck.column_add('in:Inbox');
        new_mailpile.plugins.maildeck.column_add('in:New');

    },
    activity_setup: function() {
      
      console.log('This should add Inbox & New cols');
      
    },
    makeid: function() {
        var text = "";
        var possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

        for( var i=0; i < 5; i++ ) {
            text += possible.charAt(Math.floor(Math.random() * possible.length));
        }

        return text;
    },
    columns: {},
    column_add: function(search) {
        for (s in this.columns) {
            if (this.columns[s].search == search) {
                $("#" + s)
                    .animate( { opacity: 0.4 }, 300 )
                    .animate( { opacity: 1.0 }, 300 );
                return s;
            }
        }
        var id = "col" + new_mailpile.plugins.maildeck.makeid();
        var type = "Search:";
        $(".piledeck-column-container").append(
              '<div id="' + id + '"" class="piledeck-column">'
            + '    <div class="piledeck-column-header">'
            + '       <span class="type">' + type + '</span>'
            + '       <span class="title">' + search + '</span>'
            + '       <a onclick="piledeck.column_del(\'' + id + '\')">'
            + '           <span class="icon-circle-x"></span>'
            + '       </a>'
            + '       <span class="refresh"></span>'
            + '     </div>'
            + '     <div class="entries"></div>'
            + '</div>');
        this.columns[id] = {
            search:     search,
            lastresult: null,
            countdown:  5,
        };
        this.column_refresh(id);
        this.column_start_refresh(id);
        return id;
    },
    column_del: function(id) {
        this.column_stop_refresh(id);
        delete this.columns[id];
        $("#" + id).remove();
    },
    refresh: function() {
        for (var id in this.columns) {
            this.refresh_column(id);
        }
    },
    column_refresh: function(id) {
        var col = this.columns[id];
        var self = this;
        mailpile.command(mailpile.api.search + "?q=" + col["search"], {}, "GET", function(data) {
            self.columns[id]["lastresult"] = data;
            self.column_render(id);
        });
    },
    column_render: function(id) {
        var result = this.columns[id].lastresult.result;
        var thread_ids = result.thread_ids.reverse();
        for (mid in thread_ids) {
            mid = thread_ids[mid];
            var metadata = result.data.metadata[mid];
            var messages = result.data.messages[mid];

            if ($("#" + id + " #mid_" + mid).length) {
                // Do nothing...
            } else {
                var subject = metadata.subject.substr(0, 100);
                if (metadata.subject.length > 100) { 
                    subject += "...";
                }
                tagclasses = "";
                for (tid in metadata.tag_tids) {
                    tid = metadata.tag_tids[tid];
                    tagclasses += " in_" + result.data.tags[tid].slug;
                }
                $("#"+id + " .entries").prepend(
                      '<div class="piledeck-entry' + tagclasses + '" id="mid_' + mid + '">'
                    + '<div class="actions">'
                    + '    <a href="#"><span class="icon-reply"></span></a>'
                    + '    <a href="#"><span class="icon-forward"></span></a>'
                    + '    <a href="#"><span class="icon-tag"></span></a>'
                    + '    <a href="#"><span class="icon-later"></span></a>'
                    + '</div>'
                    + '<div class="from">'
                         + metadata.from.fn 
                         + ' &lt;' + metadata.from.email + '&gt;'
                    + '</div>'
                    + '<div class="subject"><a href="http://localhost:33411/thread/=' + mid + '/">' + subject + '</a></div>'
                    + '</div>');
            }
        }
    },
    column_stop_refresh: function(id) {
        window.clearInterval(this.columns[id].refresh);
        this.columns[id].countdown = 5;
    },
    column_start_refresh: function(id) {
        var self = this;
        window.setInterval(function() { 
            if (self.columns[id].countdown == 0) {
                self.column_refresh(id); 
                self.columns[id].countdown = 5;
            } else {
                self.columns[id].countdown--;
            }
            $("#" + id + " .refresh").html(self.columns[id].countdown);
        }, 1000);
    },
    runsearch: function() {
        this.column_add($('#search-query').val());
        $('#search-query').val("");
        return false;
    }
};
