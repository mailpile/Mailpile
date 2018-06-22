import shutil


def bind(build):

    @build.provide('export')
    def provide_export(build, keyword):
        '''
        Export build artifacts to arbitrary locations. Configured via a dictionary
        of { dependency: export_path }.
        '''

        for dependency, export_path in build.config(keyword).items():
            build.log().info("Exporting '{}' to '{}'...".format(dependency,
                                                                export_path))
            dep_path = build.depend(dependency)
            shutil.copytree(dep_path, export_path)

    @build.default_config('export')
    def config_export(keyword):
        '''
        Default is to export nothing.
        '''

        return {}
