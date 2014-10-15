Mailpile.focus_search = function() {
    $("#search-query").focus(); return false;
};


/* Search - Action Select */
Mailpile.pile_action_select = function(item) {

    // Add To Data Model
    Mailpile.bulk_cache_add('messages_cache', item.data('mid'));

    // Add Tags
    var metadata = _.findWhere(Mailpile.instance.metadata, { mid: item.attr('data-mid') });
    if (metadata) {
      _.each(metadata.tag_tids, function(tid, key) {
        var tag = _.findWhere(Mailpile.instance.tags, { tid: tid });
        if (tag.type === 'tag') {
          if (_.indexOf(Mailpile.tags_cache, tag.tid) === -1) {
            Mailpile.tags_cache.push(tag.tid);
          }
        }
      });
    }

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

    // Remove Tags
    var metadata = _.findWhere(Mailpile.instance.metadata, { mid: item.attr('data-mid') });
    _.each(metadata.tag_tids, function(tid, key) {
      var tag = _.findWhere(Mailpile.instance.tags, { tid: tid });
      if (tag.type === 'tag') {
        if (_.indexOf(Mailpile.tags_cache, tag.tid) > -1) {
          Mailpile.tags_cache = _.without(Mailpile.tags_cache, tag.tid);
        }
      }
    });

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
    url = "{{ config.sys.subdirectory }}/api/0/search/as.jhtml?" + $.param(Mailpile.instance.state.query_args);
    $.getJSON(url, {}, function(data) {
        if (data.status == "success") {
            $("#content-view").html(data.result);
        }
        console.log(data);
    });
};


Mailpile.render_modal_tags = function() {
  if (Mailpile.messages_cache.length) {

    // Open Modal with selection options
    Mailpile.API.tags_get({}, function(data) {

      var tag_template = _.template($('#template-modal-tag-picker-item').html());
      var priority_html = '';
      var tags_html     = '';
      var archive_html  = '';

      /// Show tags in selected messages
      var selected_tids = {};
      _.each(Mailpile.messages_cache, function(mid, key) {
        var metadata = _.findWhere(Mailpile.instance.metadata, { mid: mid });
        _.each(metadata.tag_tids, function(tid, key) {
          if (selected_tids[tid] === undefined) {
            selected_tids[tid] = 1;
          } else {
            selected_tids[tid]++;
          }
        });
      });

      // Build Tags List
      _.each(data.result.tags, function(tag, key) {
        if (tag.display === 'priority' && tag.type === 'tag') {
          priority_data  = _.extend(tag, { selected: selected_tids });
          priority_html += tag_template(priority_data);
        }
        else if (tag.display === 'tag' && tag.type === 'tag') {
          tag_data   = _.extend(tag, { selected: selected_tids });
          tags_html += tag_template(tag_data);
        }
        else if (tag.display === 'archive' && tag.type === 'tag') {
          archive_data  = _.extend(tag, { selected: selected_tids });
          archive_html += tag_template(archive_data);
        }
      });

      var modal_template = _.template($("#modal-tag-picker").html());
      $('#modal-full').html(modal_template({ priority: priority_html, tags: tags_html, archive: archive_html }));
      $('#modal-full').modal({ backdrop: true, keyboard: true, show: true, remote: false });
    });
 
  } else {
    Mailpile.notification({ status: 'info', message: '{{_("No Messages Selected")}}' });
  }
};


$(document).ready(function() {

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
});
