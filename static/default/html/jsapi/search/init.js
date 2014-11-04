/* Search */

Mailpile.Search = {};
Mailpile.Search.Tooltips = {};

Mailpile.Search.init = function() {

  // Drag Items
  Mailpile.UI.Search.Draggable('td.draggable');
  Mailpile.UI.Search.Dropable('#pile-results tr', 'a.sidebar-tag');
  Mailpile.UI.Sidebar.Droppable('li.sidebar-tags-draggable', 'td.draggable');


  // Render Display Size
  if (!localStorage.getItem('view_size')) {
    localStorage.setItem('view_size', Mailpile.config.web.display_density);
  }

  Mailpile.pile_display(localStorage.getItem('view_size'));

  // Display Select
  $.each($('a.change-view-size'), function() {
    if ($(this).data('view_size') == localStorage.getItem('view_size')) {
      $(this).addClass('view-size-selected');
    }
  });

  // Tooltips
  Mailpile.Search.Tooltips.MessageTags();

  /* STUFF Smari added for notifications
  $("#pile-newmessages-notification").click(Mailpile.update_search);

  EventLog.subscribe(".commands.Rescan-DISABLED", function(ev) {

    if (ev.flags.indexOf("R") != -1) {
      console.log("Started rescanning...");
      $("#logo-bluemail").fadeOut(2000);
      $("#logo-redmail").hide(2000);
      $("#logo-greenmail").hide(3000);
      $("#logo-bluemail").fadeIn(2000);
      $("#logo-greenmail").fadeIn(4000);
      $("#logo-redmail").fadeIn(6000);
    }

    if (ev.flags.indexOf("c") != -1 && ev.data.messages > 0) {
      $("#pile-newmessages-notification").slideDown("slow");

      if (Notification.permission == "granted") {
        new Notification(ev.data.messages + "{{_(' new messages received')}}", { 
            body:'{{_("Your pile is growing...")}}',
            icon:'/static/img/logo-color.png', 
          }  
        )
      }
    }
  });
  */

};