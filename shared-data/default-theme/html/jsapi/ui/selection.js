/* This is the shared selection code (checkboxes etc).
** 
** Instead of a global object tracking which objects are selected, selection
** counts are calculated on-the-fly by evaluating the DOM.
**
** Selection contexts are grouped using the class "selection-context"; any
** checkboxes contained within the same selection context are assumed to be
** of the same type.
**
** The rationale for doing this, is it allows a single screen to have
** multiple groups of selectable items, each of which can be manipulated
** independently of the others. This should makes selection behavior stable,
** no matter how updates happen (AJAX, js, ...).
*/
Mailpile.UI.Selection = (function(){

var update_callbacks = {};

/* Helpers... */
function _call_callbacks(context, selected) {
  for (var i in update_callbacks) {
    update_callbacks[i](context, selected);
  }
}
function context(selector) {
  return $(selector).eq(0).closest('.selection-context').eq(0);
}
function _select_all(ctx) {
  return ctx.find('#pile-select-all-action');
}
function _each_checkbox(ctx, func) {
  ctx.find('input[type=checkbox]').each(func);
}


/**
 * Register a callback function, invoked when selection state changes
 * @param {String} name - Callback name
 * @param {Function} callback - Callback function
 */
function register(name, callback) {
  update_callbacks[name] = callback;
}

/**
 * Unregister a callback function
 * @param {String} name - Callback name
 */
function unregister(name) {
  delete update_callbacks[name];
}

/**
 * Select "these", all visible elements on page
 * @param {String|Object} selector - A JQuery selector or DOM element
 * @param {Boolean} [no_callbacks] - Skip invoking callbacks
 * @return {Array} Array of selected values
 */
function select_these(selector, no_callbacks) {
  var ctx = context(selector);
  var sel = [];
  _each_checkbox(ctx, function() {
    if (this.value == '!all') this.value = '';
    if (this.value != '') sel.push(this.value);
    $(this).prop('checked', true);
  });
  if (!no_callbacks) _call_callbacks(ctx, sel);
  return sel;
}

/**
 * Select nothing
 * @param {String|Object} selector - A JQuery selector or DOM element
 * @param {Boolean} [no_callbacks] - Skip invoking callbacks
 * @return {Array} Array of selected values, should be []
 */
function select_none(selector, no_callbacks) {
  var ctx = context(selector);
  _each_checkbox(ctx, function() {
    if (this.value == '!all') this.value = '';
    $(this).prop('checked', false);
  });
  if (!no_callbacks) _call_callbacks(ctx, []);
  return [];
}

/**
 * Select "all", potentially including things not visible on page
 * @param {String|Object} selector - A JQuery selector or DOM element
 * @param {Boolean} [no_callbacks] - Skip invoking callbacks
 * @return {Array} Array of selected values, should be ['!all']
 */
function select_all(selector, no_callbacks) {
  var ctx = context(selector);
  Mailpile.UI.Selection.select_these(ctx, true);
  _select_all(ctx).val('!all');
  if (!no_callbacks) _call_callbacks(ctx, ['!all']);
  return ['!all'];
}

/**
 * Stop selecting "all"
 * @param {String|Object} selector - A JQuery selector or DOM element
 * @param {Boolean} [no_callbacks] - Skip invoking callbacks
 * @return {Array} Array of selected values
 */
function select_not_all(selector, no_callbacks) {
  var ctx = context(selector);
  _select_all(ctx).val('');
  var sel = Mailpile.UI.Selection.selected(ctx);
  if (!no_callbacks) _call_callbacks(ctx, sel);
  return sel;
}

/**
 * Returns a list of currently selected items.
 * @param {String|Object} selector - A JQuery selector or DOM element
 * @return {Array} Array of selected values or ['!all']
 */
function selected(selector) {
  var ctx = context(selector);
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

/**
 * Returns the number of selected items or a translation of "all".
 * @param {Array} Array of selected values or ['!all']
 * @return {String} Length of selection as a string
 */
function human_length(selection) {
  if (selection && selection[0] != '!all') return ('' + selection.length);
  return '{{_("All")|escapejs}}';
}

return {
  'register': register,
  'unregister': unregister,
  'context': context,
  'select_these': select_these,
  'select_none': select_none,
  'select_all': select_all,
  // From the Zoolander school for kids who want to learn
  // to code good and do other stuff good too!
  'select_not_all': select_not_all,
  'selected': selected,
  'human_length': human_length
}})();
