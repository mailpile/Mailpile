/* UI */

Mailpile.UI = {
  content_setup: [],
  modal_options: { backdrop: true, keyboard: true, show: true, remote: false },
  Favico: new Favico({animation:'none'}),

  Crypto: {},
  Sidebar: {},
  Modals: {},
  Tooltips: {},
  Message: {},
  Search: {}
};


Mailpile.UI.prepare_new_content = function(content) {
  var $content = $(content);

  // Iterate through the list of setup callbacksk, so different parts of
  // the JS app, plugins included, can mess with the new content.
  for (var i in Mailpile.UI.content_setup) {
    Mailpile.UI.content_setup[i]($content);
  }

  // Check if this update tells us new things about the Inbox unread count,
  // update the Favico if so.
  // FIXME: This will not update the favico if the sidebar is not visible.
  var inbox_new = $content.find('.sidebar-tag-inbox').data('new');
  if (inbox_new !== undefined) {
    setTimeout(function() { Mailpile.UI.Favico.badge(inbox_new); }, 250);
  }
};

Mailpile.UI.get_modal = function() {
  return $("#modal-full");
};

Mailpile.UI.is_modal_active = function() {
  var modal = Mailpile.UI.get_modal();
  var modalData = modal.data("bs.modal");
  if(modalData === undefined) {
    // The modal has not yet been initialized.
    return false;
  } else {
    return modalData.isShown;
  }
};

Mailpile.UI.hide_modal = function() {
  if (Mailpile.UI.is_modal_active()) {
    Mailpile.UI.get_modal().modal('hide');
  }
  $('.modal-backdrop').remove();
};

Mailpile.UI.show_modal = function(html) {
  var modal = Mailpile.UI.get_modal();
  if (html) {
    modal.html(html);
  }
  modal.modal(Mailpile.UI.modal_options);
  Mailpile.UI.prepare_new_content(modal);
  return modal;
};

Mailpile.UI.init = function() {
  // BRE: disabled for now, it doesn't really work
  // Show Typeahead
  //Mailpile.activities.render_typeahead();

  // Start Eventlog
  setTimeout(function() {

    // make event log start async (e.g. for proper page load event handling)
    EventLog.timer = $.timer();
    EventLog.timer.set({ time : 22500, autostart : false });
    EventLog.poll();

    // Run Composer Autosave
    Mailpile.Composer.AutosaveTimer.play();
    Mailpile.Composer.AutosaveTimer.set({ time : 20000, autostart : true });

  }, 200);

  // Register callbacks etc on new content: the whole page is new!
  Mailpile.UI.prepare_new_content(document);
};


Mailpile.UI.tag_icons_as_lis = function() {
  var icons_html = '';
  $.each(Mailpile.theme.icons, function(key, icon) {
    icons_html += ('<li class="modal-tag-icon-option ' + icon +
                   '" data-icon="' + icon + '"></li>');
  });
  return icons_html;
};


Mailpile.UI.tag_colors_as_lis = function() {
  var sorted_colors =  _.keys(Mailpile.theme.colors).sort();
  var colors_html = '';
  $.each(sorted_colors, function(key, name) {
    var hex = Mailpile.theme.colors[name];
    colors_html += ('<li><a href="#" class="modal-tag-color-option" ' +
                    'style="background-color: ' + hex + '" data-name="' +
                    name + '" data-hex="' + hex + '"></a></li>');
  });
  return colors_html;
};
