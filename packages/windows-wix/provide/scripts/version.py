def bind(framework):

    @framework.provide('version')
    def provide_version(build, keyword):
        mailpile_dir = build.depend('mailpile')
        util = build.depend('util')
        build.depend('python27')

        with util.pushdir(mailpile_dir):
            version = build.invoke('python', 'scripts\\version.py').strip()
            build.log().info("Version string is: " + version)

        return version
