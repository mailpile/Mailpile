// HTML mail display & sandboxing


Mailpile.Message.ShowHTMLLegacy = function(mid, $old_message_body, html_data) {
  // Inject iframe
  $old_message_body.append(
    '<iframe id="message-iframe-' + mid + '" class="message-part-html"' +
    ' sandbox="allow-top-navigation allow-popups allow-popups-to-escape-sandbox"' +
    ' seamless target="_blank" srcdoc=""></iframe>');

  // Add html parts
  var html_parts = '';
  _.each(html_data, function(part, key) {
    html_parts += part.data;
  });
  $('#message-iframe-' + mid).attr('srcdoc', DOMPurify.sanitize(html_parts));

  // Resize & Style
  setTimeout(function() {
    var iframe_height = $('#message-iframe-' + mid).contents().height();
    $('#message-iframe-' + mid).height(iframe_height);
    $('#message-iframe-' + mid).contents().find('body').addClass('message-part-html-text');
  }, 100);
};


Mailpile.Message.AddDOMPurifyHooks = function(with_image_proxy,
                                              changes_callback) {
  // The following code is based on dompurify/demos/hooks-proxy-demo.html and
  // the whiteout.io sandbox implementation.
  function proxy() {
    if (changes_callback) changes_callback();
    if (with_image_proxy) {
      return (
        Mailpile.API._sync_url +
        Mailpile.API._endpoints['http_proxy_get'] +
        '?csrf=' +
        Mailpile.csrf_token +
        '&url='
      );
    }
    else {
      // Replace all images with a 1x100 transparent PNG, yay!
      // Note: using a 1x1 square results in large square empty
      //       spaces in many e-mails, because only the width is
      //       defined in the HTML; and the hight gets scaled
      //       proportionally. Thus the 1x100 ratio instead.
      return Mailpile.API.U('/static/img/1x100.png#old=');
    }
  }

  // Specify attributes to proxy
  var attributes = ['background', 'href', 'src'];  // not: 'action', 'poster'

  // specify the regex to detect external content
  var url_regex = /(url\("?)(?!data:)/gim;

  /**
   *  Take CSS property-value pairs and proxy URLs in values,
   *  then add the styles to an array of property-value pairs
   */
  function addStyles(output, styles) {
    for (var prop = styles.length-1; prop >= 0; prop--) {
      if (styles[styles[prop]]) {
        var url = styles[styles[prop]].replace(url_regex, '$1' + proxy());
        styles[styles[prop]] = url;
      }
      if (styles[styles[prop]]) {
        output.push(styles[prop] + ':' + styles[styles[prop]] + ';');
      }
    }
  }

  /**
   * Take CSS rules and analyze them, proxy URLs via addStyles(),
   * then create matching CSS text for later application to the DOM
   */
  function addCSSRules(output, cssRules) {
    for (var index=cssRules.length-1; index>=0; index--) {
      var rule = cssRules[index];
      // check for rules with selector
      if (rule.type == 1 && rule.selectorText) {
        output.push(rule.selectorText + '{')
        if (rule.style) {
          addStyles(output, rule.style)
        }
        output.push('}');
      // check for @media rules
      } else if (rule.type === rule.MEDIA_RULE) {
        output.push('@media ' + rule.media.mediaText + '{');
        addCSSRules(output, rule.cssRules)
        output.push('}');
      // check for @font-face rules
      } else if (rule.type === rule.FONT_FACE_RULE) {
        output.push('@font-face {');
        if (rule.style) {
          addStyles(output, rule.style)
        }
        output.push('}');
      // check for @keyframes rules
      } else if (rule.type === rule.KEYFRAMES_RULE) {
        output.push('@keyframes ' + rule.name + '{');
        for (var i=rule.cssRules.length-1;i>=0;i--) {
          var frame = rule.cssRules[i];
          if (frame.type === 8 && frame.keyText) {
            output.push(frame.keyText + '{');
            if (frame.style) {
              addStyles(output, frame.style);
            }
            output.push('}');
          }
        }
        output.push('}');
      }
    }
  }

  /**
   * Proxy a URL in case it's not a Data URI
   */
  function proxyAttribute(url) {
    if (/^data:image\//.test(url)) {
      return url;
    } else {
      return proxy() + encodeURIComponent(url)
    }
  }

  // Add a hook to enforce proxy for leaky CSS rules
  DOMPurify.removeHooks('uponSanitizeElement');
  DOMPurify.addHook('uponSanitizeElement', function (node, data) {
    if (data.tagName === 'style') {
      var output  = [];
      addCSSRules(output, node.sheet.cssRules);
      node.textContent = output.join("\n");
    }
  });

  DOMPurify.removeHooks('afterSanitizeAttributes');
  DOMPurify.addHook('afterSanitizeAttributes', function(node) {
    if ('target' in node) {
      // This is a belt-and-suspenders thing, in case the load()
      // event below does not fire.
      node.setAttribute('target', '_blank');
    }
    else if (node.hasAttribute('xlink:href') ||
             node.hasAttribute('href')) {
      node.setAttribute('xlink:show', 'new');
    }

    // Check all src attributes and proxy them
    if (node.nodeName != 'A') {
      for(var i = 0; i <= attributes.length-1; i++) {
        if (node.hasAttribute(attributes[i])) {
          node.setAttribute(attributes[i], proxyAttribute(
            node.getAttribute(attributes[i]))
          );
        }
      }
    }

    // Check all style attribute values and proxy them
    if (node.hasAttribute('style')) {
      var styles = node.style;
      var output = [];
      for (var prop = styles.length-1; prop >= 0; prop--) {
        // we re-write each property-value pair to remove invalid CSS
        if (node.style[styles[prop]] && url_regex.test(node.style[styles[prop]])) {
          var url = node.style[styles[prop]].replace(url_regex, '$1' + proxy())
          node.style[styles[prop]] = url;
        }
        output.push(styles[prop] + ':' + node.style[styles[prop]] + ';');
      }
      // re-add styles in case any are left
      if (output.length) {
        node.setAttribute('style', output.join(""));
      } else {
        node.removeAttribute('style');
      }
    }
  });
};


Mailpile.Message.SetHTMLPolicy = function(mid, old_policy, new_policy) {
  // Record as preference on VCard
  var $from = $('.pile-message-' + mid).find('.from');
  if ($from.length > 0 && (!old_policy || old_policy != new_policy)) {
    Mailpile.API.contacts_set_post({
      'fn': $from.data('fn'),
      'email': $from.data('address'),
      'name': 'x-mailpile-html-policy',
      'value': new_policy
    });
  }
};


Mailpile.Message.SandboxHTML = function(part_id, $part, html_data, policy, allow_images) {

  var $iframe_html = (
    '<iframe id="message-iframe-' + part_id + '" seamless');
{% if config.prefs.html5_sandbox %}
  // This is the sandbox. It has issues, the browsers are still developing
  // this feature at their end!  We could disable it and rely on DOMPurify
  // entirely...
  $iframe_html += (                        // IMPORTANT: Do not allow-scripts!
    ' sandbox="allow-same-origin' +        // Let us manipulate contents
    '          allow-top-navigation' +     // For mailto:
    '          allow-popups' +             // Allow target=_blank links
    '          allow-popups-to-escape-sandbox"'); // Back to the normal web
{% endif %}
  $iframe_html += (
    ' class="message-part-html" target="_blank" srcdoc=""></iframe>');

  var $wrapper = $('<div/>');
  var $iframe = $($iframe_html);
  $iframe.load(function() {
    var $contents = $iframe.contents();

    // Make clicked links open in new window
    $contents.find('a').each(function(i, elem) {
        if (elem.href.indexOf("mailto:") == 0) {
            elem.href = Mailpile.API.U('/message/compose/?to=' +
                                       elem.href.substring(7));
        }
        else {
            $(elem).attr('target', '_blank');
        }
    });

    // Copy some defaults from our CSS...
    $contents.find('body').css('color', $part.css('color'))
                          .css('background', $part.css('background'));

    // Adjust size - the trick here is we let the $iframe load, and
    // once it is ready, we ask how big it is. We then resize the IFrame
    // to have the same width and height (to get rid of scroll bars) and
    // finally use a CSS transform to scale the whole thing down so it
    // fits again. The $wrapper keeps all this from affecting the rest
    // of the page.
    var cheight = $contents.outerHeight();
    var cwidth = $contents.outerWidth();
    var iwidth = $part.width();
    if (cwidth > iwidth) {
      var scale = iwidth / cwidth;
      if (scale < 0.6) scale = 0.6; // FIXME: Breaks ratios below
      $iframe.css({
        'width': cwidth + 'px',
        'height': (15 / scale + cheight) + 'px',
        'margin': 0, 'padding': 0,
        'transform': 'scale(' + scale + ')',
        'transform-origin': '0 0'
      });
      $wrapper.height(15 + cheight * scale);
    }
    else {
      $iframe.height(15 + cheight);
      $wrapper.height(15 + cheight);
    }
  });

  // Sanitize the HTML: the sandbox keeps Javascript from running
  // and blocks any external content-loads; we're mainly using
  // DOMPurify to rewrite image references to go through our proxy,
  // as per the code above.
  var changes = 0;
  Mailpile.Message.AddDOMPurifyHooks(allow_images && (policy == 'images'),
                                     function() { changes += 1 });
  $iframe.attr('srcdoc', DOMPurify.sanitize(html_data, {
    WHOLE_DOCUMENT: true,
  }));

  if (allow_images && (changes > 0) && (policy != 'images')) {
    $msg_details = $part.closest('.has-mid').find('.message-details');
    $msg_details.find('.html-image-question').remove();
    $msg_details.append($(
      '<div class="message-app-note html-image-question"><p>' +
      '  <span class="icon icon-eye"></span>' +
      '  {{_("This message references images or other content from the web. Downloading and displaying these images may notify the sender that you have read the mail.")|escapejs}}' +
      '</p><ul>' +
      '  <li><a class="display-now">{{_("Okay, display the images")|escapejs}}</a>' +
      '  <li><a class="display-always">{{_("Always display images from this sender")|escapejs}}</a>' +
      '  <li><a class="dismiss">{{_("No, thanks!")|escapejs}}</a>' +
      '</ull></div>'
    ));
    $msg_details.find('.display-now').click(function() {
      $wrapper.remove();
      Mailpile.Message.SandboxHTML(part_id, $part, html_data, 'images');
    });
    $msg_details.find('.display-always').click(function() {
      $wrapper.remove();
      $msg_details.find('.html-image-question').remove();
      Mailpile.Message.SandboxHTML(part_id, $part, html_data, 'images');
      Mailpile.Message.SetHTMLPolicy($part.closest('.has-mid').data('mid'),
                                     policy, 'images');
    });
    $msg_details.find('.dismiss').click(function() {
      $msg_details.find('.html-image-question').remove();
    });
  }

  // More size adjusting hackery. See comment above.
  $wrapper.css({
    'width': $part.width(),
    'margin': 0,
    'padding': 0,
    'display': 'block',
    'position': 'relative',
    'overflow': 'hidden'
  });
  $wrapper.append($iframe);
  $part.append($wrapper);
  $wrapper.width($part.width());
};


Mailpile.Message.ShowHTML = function(mid, policy, allow_images) {
  // HTML Parts Exist
  var $msg = $('#message-' + mid);
  var html_data = $msg.data('html');
  if (html_data) {
    $msg = $msg.closest('.has-mid');
    $msg.find('.pile-message-html-part').show();
    $msg.find('.html-image-question').show();
    $msg.find('.html-display-hint').hide();
    $msg.find('.message-part-text, .pile-message-text-part').hide();

    // FIXME: Legacy code, kill kill kill
    var $old_message_body = $msg.find('.thread-message-body');
    if ($old_message_body.length > 0) {
      Mailpile.Message.ShowHTMLLegacy(mid, $old_message_body, html_data);
    }
    else {
      for (var i in html_data) {
        var part_id = mid + '-' + (1 + parseInt(i));
        var $part = $('#html-part-' + part_id);
        if ($part.find('.noframe').length > 0) {
          Mailpile.Message.SandboxHTML(
            part_id, $part, html_data[i].data, policy, allow_images);
          $part.find('.noframe').remove();
        }
      }
      if (!policy || policy == 'none') {
        Mailpile.Message.SetHTMLPolicy(mid, policy, 'display');
      }
    }
  } else {
    // FIXME: Hardcoded untranslated stuff here, ick ick.
    $msg.find('.thread-message-body').append('<em>Message does not have any HTML parts</em>');
  }
};


Mailpile.Message.ShowPlain = function(mid, policy) {
  var $msg = $('#message-' + mid).closest('.has-mid');
  $msg.find('#message-iframe-' + mid).remove();
  $msg.find('.html-image-question').hide();
  $msg.find('.pile-message-html-part').hide();
  $msg.find('.message-part-text, .pile-message-text-part').show();
  Mailpile.Message.SetHTMLPolicy(mid, policy, 'none');
};
