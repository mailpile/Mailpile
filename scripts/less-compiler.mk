PATH:=$(PATH):/Applications/CodeKit.app/Contents/Resources/engines/less/bin/

static/default/css/default.css: .less-deps
	@(cd static/default/less && \
            lessc default.less \
              |perl -npe 's,(libraries|app)/,,g' \
              |perl -npe 's,/static/,../,g' \
	    >../css/default.css)
	@ls -l static/default/css/default.css

.less-deps: scripts/less-compiler.in \
	static/default/less//app/backgrounds.less\
	static/default/less//app/bulk-actions.less\
	static/default/less//app/credits.less\
	static/default/less//app/icons.less\
	static/default/less//app/messages.less\
	static/default/less//app/notifications.less\
	static/default/less//app/webfonts.less\
	static/default/less//app-mobile/global.less\
	static/default/less//app-tablet/global.less\
	static/default/less//app-web/compose.less\
	static/default/less//app-web/files.less\
	static/default/less//app-web/global.less\
	static/default/less//app-web/pile.less\
	static/default/less//app-web/search.less\
	static/default/less//app-web/sidebar.less\
	static/default/less//app-web/sub-navigation.less\
	static/default/less//app-web/tags.less\
	static/default/less//app-web/thread.less\
	static/default/less//app-web/topbar.less\
	static/default/less//config.less\
	static/default/less//default.less\
	static/default/less//libraries/jquery.qtip.less\
	static/default/less//libraries/nanoscroller.less\
	static/default/less//libraries/select2.less\
	static/default/less//mixins/animate.less\
	static/default/less//mixins/elements.less\
	static/default/less//mixins/grid.less\
	static/default/less//mixins/mailpile.less\
	static/default/less//mixins/resuable.less\
	static/default/less//mixins/shapes.less\
	static/default/less//rebar/base.less\
	static/default/less//rebar/buttons.less\
	static/default/less//rebar/clearing.less\
	static/default/less//rebar/forms.less\
	static/default/less//rebar/images.less\
	static/default/less//rebar/links.less\
	static/default/less//rebar/lists.less\
	static/default/less//rebar/navigation.less\
	static/default/less//rebar/responsive-boxes.less\
	static/default/less//rebar/responsive-grid.less\
	static/default/less//rebar/separators.less\
	static/default/less//rebar/tables.less\
	static/default/less//rebar/typography.less\

	@touch .less-deps