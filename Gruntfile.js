module.exports = function(grunt) {

  grunt.registerTask('watch', [ 'watch' ]);

  grunt.initConfig({
    concat: {
      js: {
        options: {
          separator: ';'
        },
        src: [
          'static/default/js/libraries.js',
          'static/default/js/helpers.js',
          'bower_components/html5shiv/dist/html5shiv.js',
          'bower_components/underscore/underscore.js',
          'bower_components/backbone/backbone.js',
          'bower_components/backbone-validation/dist/backbone-validation.js',
          'bower_components/bootstrap/js/dropdown.js',
          'bower_components/bootstrap/js/modal.js',
          'bower_components/jquery-slugify/dist/slugify.js',
          'bower_components/jquery.ui/ui/jquery.ui.core.js',
          'bower_components/jquery.ui/ui/jquery.ui.widget.js',
          'bower_components/jquery.ui/ui/jquery.ui.mouse.js',
          'bower_components/jquery.ui/ui/jquery.ui.draggable.js',
          'bower_components/jquery.ui/ui/jquery.ui.droppable.js',
          'bower_components/jquery.ui/ui/jquery.ui.sortable.js',
          'bower_components/jquery.ui/ui/jquery.autoresize.js',
          'bower_components/jquery-timer/jquery.timer.js',
          'bower_components/mousetrap/mousetrap.js',
          'static/default/js/mousetrap.global.bind.js',
          'bower_components/listjs/dist/list.js',
          'bower_components/purl/purl.js',
          'bower_components/qtip2/jquery.qtip.js',
          'bower_components/favico.js/favico.js',
          'bower_components/select2/select2.js',
          'bower_components/typeahead.js/dist/typeahead.jquery.js'
        ],
        dest: 'static/default/js/libraries.min.js'
      },
    },
    uglify: {
      options: {
        mangle: false
      },
      js: {
        files: {
          'static/default/js/libraries.min.js': ['static/default/js/libraries.min.js']
        }
      }
    },
    less: {
      options: {
        cleancss: true
      },
      style: {
        files: {
          "static/default/css/default.css": "static/default/less/default.less"
        }
      }
    },
    watch: {
      js: {
        files: ['static/default/js/*.js'],
        tasks: ['concat:js', 'uglify:js'],
        options: {
          livereload: true,
        }
      },
      css: {
        files: ['static/default/less/default.less'],
        tasks: ['less:style'],
        options: {
          livereload: true,
        }
      }
    }
  });

  grunt.loadNpmTasks('grunt-contrib-concat');
  grunt.loadNpmTasks('grunt-contrib-uglify');
  grunt.loadNpmTasks('grunt-contrib-less');
  grunt.loadNpmTasks('grunt-contrib-watch');

};