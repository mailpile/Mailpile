module.exports = function(grunt) {

  grunt.registerTask('watch', [ 'watch' ]);

  grunt.initConfig({
    concat: {
      js: {
        options: {
          separator: ';'
        },
        src: [
          'mailpile/www/default/js/libraries.js',
          'mailpile/www/default/js/helpers.js',
          'bower_components/underscore/underscore.js',
          'bower_components/backbone/backbone.js',
          'bower_components/backbone-validation/dist/backbone-validation.js',
          'bower_components/jquery.ui/ui/jquery.ui.core.js',
          'bower_components/jquery.ui/ui/jquery.ui.widget.js',
          'bower_components/jquery.ui/ui/jquery.ui.mouse.js',
          'bower_components/jquery.ui/ui/jquery.ui.draggable.js',
          'bower_components/jquery.ui/ui/jquery.ui.droppable.js',
          'bower_components/jquery.ui/ui/jquery.ui.sortable.js',
          'bower_components/jquery-autosize/jquery.autosize.js',
          'bower_components/jquery-timer/jquery.timer.js',
          'bower_components/qtip2/jquery.qtip.js',
          'bower_components/jquery-slugify/dist/slugify.js',
          'bower_components/typeahead.js/dist/typeahead.jquery.js',
          'bower_components/bootstrap/js/dropdown.js',
          'bower_components/bootstrap/js/modal.js',
          'bower_components/mousetrap/mousetrap.js',
          'mailpile/www/default/js/mousetrap.global.bind.js',
          'bower_components/listjs/dist/list.js',
          'bower_components/purl/purl.js',
          'bower_components/favico.js/favico.js',
          'bower_components/select2/select2.js'
        ],
        dest: 'mailpile/www/default/js/libraries.min.js'
      },
    },
    uglify: {
      options: {
        mangle: false
      },
      js: {
        files: {
          'mailpile/www/default/js/libraries.min.js': ['mailpile/www/default/js/libraries.min.js']
        }
      }
    },
    less: {
      options: {
        cleancss: true
      },
      style: {
        files: {
          "mailpile/www/default/css/default.css": "mailpile/www/default/less/default.less"
        }
      }
    },
    watch: {
      js: {
        files: ['mailpile/www/default/js/*.js'],
        tasks: ['concat:js', 'uglify:js'],
        options: {
          livereload: true,
        }
      },
      css: {
        files: [
          'mailpile/www/default/less/config.less',
          'mailpile/www/default/less/default.less',
          'mailpile/www/default/less/app/*.less',
          'mailpile/www/default/less/libraries/*.less'
        ],
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