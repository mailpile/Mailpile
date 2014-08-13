/* Setup - Tooltips */
var TooltipsView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function() {
    return this;
  },
  showProgress: function() {
    $('.setup-progress-circle').qtip({
      style: {
       tip: {
          corner: 'bottom center',
          mimic: 'bottom center',
          border: 0,
          width: 10,
          height: 10
        },
        classes: 'qtip-tipped'
      },
      position: {
        my: 'bottom center',
        at: 'top center',
  			viewport: $(window),
  			adjust: {
  				x: 0,  y: -5
  			}
      },
      show: {
        delay: 350
      }
    });
  },
  showSourceConfigure: function() {
    $('.setup-tooltip').qtip({
      style: {
       tip: {
          corner: 'bottom center',
          mimic: 'bottom center',
          border: 0,
          width: 10,
          height: 10
        },
        classes: 'qtip-tipped'
      },
      position: {
        my: 'bottom center',
        at: 'top center',
  			viewport: $(window),
  			adjust: {
  				x: 0,  y: 5
  			}
      },
      show: {
        delay: 350
      }
    });
  }
});