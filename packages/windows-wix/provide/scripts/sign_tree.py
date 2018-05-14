
def bind(build):
    @build.provide('sign_tree')
    def provide_sign_tree(build, keyword):
        build.depend('signtool')
        try:
            key = build.config('signing_key')

            # TODO: publish a recursive scanner.

        except KeyError:
            build.log().warning('No signing key configured--outputs will not be signed')

            def sign_tree(path):
                build.log().info("ignoring request to sign tree '{}'".format(path))

        build.publish(keyword, sign_tree)

        return None
