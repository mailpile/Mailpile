/* JS App Files */
{% include("jsapi/setup/magic.js") %}
{% include("jsapi/setup/passphrase.js") %}
{% include("jsapi/setup/state.js") %}
{% include("jsapi/setup/home.js") %}
{% include("jsapi/setup/profiles.js") %}
{% include("jsapi/setup/profiles_settings.js") %}
{% include("jsapi/setup/sources.js") %}
{% include("jsapi/setup/sources_settings.js") %}
{% include("jsapi/setup/sources_configure.js") %}
{% include("jsapi/setup/sending.js") %}
{% include("jsapi/setup/security.js") %}
{% include("jsapi/setup/backups.js") %}
{% include("jsapi/setup/access.js") %}
{% include("jsapi/setup/language.js") %}
{% include("jsapi/setup/complete.js") %}
{% include("jsapi/setup/tooltips.js") %}
{% include("jsapi/setup/router.js") %}

/* Validation UI Feedback */
_.extend(Backbone.Validation.callbacks, {
  valid: function(view, attr, selector) {
    var msg = $('#validation-' + attr).find('.validation-message').data('message');
    $('#validation-' + attr).find('.validation-message').html(msg).removeClass('validation-error');
    $('#validation-' + attr).find('[' + selector + '=' + attr +']').removeClass('validation-error');
  },
  invalid: function(view, attr, error, selector) {
    var message = $('#validation-' + attr).find('.validation-message').html();
    $('#validation-' + attr).find('.validation-message').data('message', message)
    $('#validation-' + attr).find('.validation-message').html(error).addClass('validation-error');
    $('#validation-' + attr).find('[' + selector + '=' + attr +']').addClass('validation-error');
  }
});
