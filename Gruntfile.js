module.exports = function(grunt) {

  grunt.registerTask('watch', [ 'watch' ]);

  grunt.initConfig({
    concat: {
      js: {
        options: {
          separator: ';'
        },
        src: [
          'bower_components/jquery/dist/jquery.min.js',
          'bower_components/underscore/underscore-min.js',
          'bower_components/jquery-timer/jquery.timer.js',
          'bower_components/autosize/dist/autosize.js',
          'bower_components/mousetrap/mousetrap.js',
          'shared-data/default-theme/js/mousetrap.global.bind.js',
          'bower_components/jquery.ui/ui/jquery.ui.core.js',
          'bower_components/jquery.ui/ui/jquery.ui.widget.js',
          'bower_components/jquery.ui/ui/jquery.ui.mouse.js',
          'bower_components/jquery.ui/ui/jquery.ui.draggable.js',
          'bower_components/jquery.ui/ui/jquery.ui.droppable.js',
          'bower_components/jquery.ui/ui/jquery.ui.sortable.js',
          'bower_components/jqueryui-touch-punch/jquery.ui.touch-punch.js',
          'bower_components/qtip2/basic/jquery.qtip.min.js',
          'bower_components/jquery-slugify/dist/slugify.js',
          'bower_components/typeahead.js/dist/typeahead.jquery.js',
          'bower_components/bootstrap/js/dropdown.js',
          'bower_components/bootstrap/js/modal.js',
          'bower_components/favico.js/favico.js',
          'bower_components/select2/select2.min.js',
          'bower_components/moxie/bin/js/moxie.min.js',
          'bower_components/plupload/js/plupload.min.js',
          'bower_components/dompurify/dist/purify.min.js'
        ],
        dest: 'shared-data/default-theme/js/libraries.min.js'
      }
    },
    uglify: {
      options: {
        mangle: false
      },
      js: {
        files: {
          'shared-data/default-theme/js/libraries.min.js': ['shared-data/default-theme/js/libraries.min.js']
        }
      }
    },
    less: {
      options: {
        cleancss: true
      },
      style: {
        files: {
          "shared-data/default-theme/css/default.css": "shared-data/default-theme/less/default.less"
        }
      }
    },
    watch: {
      js: {
        files: ['shared-data/default-theme/js/*.js'],
        tasks: ['concat:js', 'uglify:js'],
        options: {
          livereload: true,
        }
      },
      css: {
        files: [
          'shared-data/default-theme/less/config.less',
          'shared-data/default-theme/less/default.less',
          'shared-data/default-theme/less/app/*.less',
          'shared-data/default-theme/less/libraries/*.less'
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
