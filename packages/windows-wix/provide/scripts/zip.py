import zipfile


def bind(build):

    @build.provide('wix', 'tor', 'lessmsi', 'openssl', 'resource_hacker')
    def provide_zip(build, keyword):
        '''
        Inflate zip files into the build path
        '''

        build.depend('root')
        util = build.depend('util')
        dep_path = build.invoke('path', keyword)
        zip_path = build.cache().resource(keyword)
        archive = zipfile.ZipFile(zip_path)
        archive.extractall(dep_path)
        util.publish_exes(build, dep_path)
        return dep_path
