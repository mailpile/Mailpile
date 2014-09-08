/* Setup - Tooltips */
var TooltipsView = Backbone.View.extend({
  initialize: function() {
		this.render();
  },
  render: function() {
    return this;
  },
  showProgressCircles: function(view) {
    var view = view.split('/')[0];
    _.each(StateModel.attributes.result, function(val, key) {
      if (view === '#' + key) {
        $('li.setup-progress-' + key).find('a.setup-progress-circle').addClass('on');        
      }
      else if (val) {
        $('li.setup-progress-' + key).find('a.setup-progress-circle').addClass('complete');
      }
      else {
        $('li.setup-progress-' + key).find('a.setup-progress-circle').removeClass('complete on');
      }
    });
  },
  showHelp: function() {
    $('.setup-help-tooltip').qtip({
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
  				x: 0,  y: -3
  			}
      },
      show: {
        delay: 350
      }
    });
  },
  showProgress: function() {
    $('.setup-progress-circle').qtip({
      style: {
       tip: {
          corner: 'top center',
          mimic: 'top center',
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