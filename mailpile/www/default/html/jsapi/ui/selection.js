/* This is the shared selection code (checkboxes etc).
** 
** Instead of a global object tracking which objects are selected, selection
** counts are calculated on-the-fly by evaluating the DOM.
**
** The rationale for doing this, is it allows a single screen to have
** multiple groups of selectable items, each of which can be manipulated
** independently of the others. This should makes selection behavior stable,
** no matter how updates happen (AJAX, js, ...).
*/
Mailpile.UI.Selection = (function(){

var update_callbacks = {};

function _call_callbacks(context, selected) {
  for (var i in update_callbacks) {
    update_callbacks[i](context, selected);
  }
}

function _context(selector) {
  return $(selector);
}

function _select_all(ctx) {
  return ctx.find('#pile-select-all-action');
}

function _each_checkbox(ctx, func) {
  ctx.find('input[type=checkbox]').each(func);
}


return {

  /**
   * Register a callback function, invoked when selection state changes
   * @param {String} name - Callback name
   * @param {Function} callback - Callback function
   */
  register: function(name, callback) {
    update_callbacks[name] = callback;
  },

  /**
   * Unregister a callback function
   * @param {String} name - Callback name
   */
  unregister: function(name) {
    delete update_callbacks[name];
  },


  /**
   * Select "these", all visible elements on page
   * @param {String|Object} selector - A JQuery selector or DOM element
   * @param {Boolean} [no_callbacks] - Skip invoking callbacks
   * @return {Array} Array of selected values
   */
  select_these: function(selector, no_callbacks) {
    var ctx = _context(selector);
    var sel = [];
    _each_checkbox(ctx, function() {
      if (this.value == '!all') this.value = '';
      if (this.value != '') sel.push(this.value);
      $(this).prop('checked', true)
             .closest('tr', ctx).addClass('result-on');
    });
    if (!no_callbacks) _call_callbacks(ctx, sel);
    return sel;
  },

  /**
   * Select nothing
   * @param {String|Object} selector - A JQuery selector or DOM element
   * @param {Boolean} [no_callbacks] - Skip invoking callbacks
   * @return {Array} Array of selected values, should be []
   */
  select_none: function(selector, no_callbacks) {
    var ctx = _context(selector);
    _each_checkbox(ctx, function() {
      if (this.value == '!all') this.value = '';
      $(this).prop('checked', false)
             .closest('tr', ctx).removeClass('result-on');
    });
    if (!no_callbacks) _call_callbacks(ctx, []);
    return [];
  },

  /**
   * Select "all", potentially including things not visible on page
   * @param {String|Object} selector - A JQuery selector or DOM element
   * @param {Boolean} [no_callbacks] - Skip invoking callbacks
   * @return {Array} Array of selected values, should be ['!all']
   */
  select_all: function(selector, no_callbacks) {
    var ctx = _context(selector);
    Mailpile.UI.Selection.select_these(ctx, true);
    _select_all(ctx).val('!all');
    if (!no_callbacks) _call_callbacks(ctx, ['!all']);
    return ['!all'];
  },

  /**
   * Stop selecting "all"
   * @param {String|Object} selector - A JQuery selector or DOM element
   * @param {Boolean} [no_callbacks] - Skip invoking callbacks
   * @return {Array} Array of selected values
   */
  select_not_all: function(selector, no_callbacks) {
    var ctx = _context(selector);
    _select_all(ctx).val('');
    var sel = Mailpile.UI.Selection.selected(ctx);
    if (!no_callbacks) _call_callbacks(ctx, sel);
    return sel;
  },

  /**
   * Returns a list of currently selected items.
   * @param {String|Object} selector - A JQuery selector or DOM element
   * @return {Array} Array of selected values or ['!all']
   */
  selected: function(selector) {
    var ctx = _context(selector);
    var selected = [];
    var all = false;
    _each_checkbox(ctx, function() {
      var $elem = $(this);
      if ($elem.is(':checked') && this.value) {
        if (this.value == '!all') all = true;
        selected.push(this.value);
      }
    });
    if (all) return ['!all'];
    return selected;
  }

}})();
