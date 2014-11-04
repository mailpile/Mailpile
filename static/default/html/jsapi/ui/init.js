/* UI */

Mailpile.UI = {
  ModalOptions: { backdrop: true, keyboard: true, show: true, remote: false }
};

Mailpile.UI.Sidebar  = {};
Mailpile.UI.Modals   = {};
Mailpile.UI.Tooltips = {};
Mailpile.UI.Message  = {};
Mailpile.UI.Search   = {};


Mailpile.UI.init = function() {

  // Favicon
  var inbox = _.findWhere(Mailpile.instance.tags, {slug: 'inbox'});
  var favicon = new Favico({animation:'popFade'});
  favicon.badge(inbox.stats.new);

  // Show Typeahead
  Mailpile.activities.render_typeahead();

  // Start Eventlog
  //EventLog.init();
  setTimeout(function() {

    // make event log start async (e.g. for proper page load event handling)
    EventLog.timer = $.timer();
    EventLog.timer.set({ time : 22500, autostart : false });
    EventLog.poll();

    // Run Composer Autosave
    if (Mailpile.instance.state.context_url === '/message/' || 
        Mailpile.instance.state.context_url === '/message/draft/') {
      Mailpile.Composer.AutosaveTimer.play();
      Mailpile.Composer.AutosaveTimer.set({ time : 20000, autostart : true });
    }

  }, 1000);


  /* Drag & Drop */
  Mailpile.UI.Sidebar.Draggable('a.sidebar-tag');


  /* Tooltips */
  Mailpile.UI.Tooltips.TopbarNav();
  Mailpile.UI.Tooltips.BulkActions();
  Mailpile.UI.Tooltips.ComposeEmail();

};
