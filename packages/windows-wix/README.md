# WIX Mailpile packaging framwork #

The WIX mailpile packaging framework automates constructing a windows package
for mailpile and it's dependencies. It attempts to pull in dependencies in as
localized/portable resources, and appropriately construct a run-time
environment on the installed machine.

The intent is for the packaging framework to *just work* assuming no interface
points between dependencies change. To do so, the framework primarily functions
around sourcing, discovery, and versioning of files. While there's a fair
amount of automation in the process, ultimately customizations are baked in to
various points in the framework.

## Producing a package ##

Producing a package has minimal requirements:

  - A windows machine (tested: win 7, win 10)
  - Python installed (tested: python 2.7.15, 3.4.3)
  - gpg4win **NOT** installed
  - git installed
  - mailpile checked out
  - administrator privileges
  - Optional software signing requirements:
      - a pkcs12 certificate suitable for software signing
      - the software signing portion of the windows sdk (~50MB)

To produce a package, go to the 'mailpile/packages/windows-wix/' directory and
run `python provide -i provide.json`. It will output a directory called
'package' in the current working directory. The msi is located in
'package/mailpile-<version>-<culture>.msi'.

To customize the build, view options by running `python provide -h`. Most can
also be passed via a configuration json--see 'provide.json' as an example. It
is also possible to output partial products by adding multiple targets to the
'export' configuration.

Note: work in progress on customization and improving automation. See TODO.md.

### Software Signing ###

Software signing is an entirely optional build step. If not configured, the
build will succeed, but produce several warnings that it was not able to sign
the contents. While functional, an unsigned build does not provide authenticity
assurances.

Software signing uses `signtool.exe` to sign recognized file types prior to
packaging, as well as the output package itself. Since Microsoft doesn't provide
a portable/stand-alone download for signtool, anyone wanting to sign a mailpile
package must install the relevant part of the windows sdk. The install feature
"Windows SDK Signing Tools for Desktop Apps" should be enough on it's own.

The packaging script will attempt to detect `signtool.exe` in it's default
install location. This can be checked by inspecting the help output from
`python provide -h`: If the default for `--config_signtool` is `signtool.exe`,
provide was not able to locate signtool on the local machine, and expects it
to exist on the system path. The location of `signtool.exe` can also be defined
by manually setting this parameter.

Actually signing software components requires a pkcs12 PKI certificate capable
of software signing. A self-signed cert can be made following these intsructions
https://stackoverflow.com/questions/9428335/make-your-own-certificate-for-signing-files

Alternately, a software signing certifacte can be sourced. Note that Microsoft
only includes select few roots of trust by default--any other CA, no matter how
valid, will not be validated a vanila windows install. Check the list carefully!

With a certificate in hand, the `--config_signing_key` and
`--config_signing_passwd` options can be set to enable software signing. Both
are required as it is assumed the key is stored in an encrypted state.
Additionally, the signing timestamp server can be configured--see
`python provide -h` for full details.

## Integration points ##

The mailpile package integrates various mailpile dependencies in various ways.
Physicially, each top-level dependency is placed in it's own sub-directory
inside the install directory. Components are logically joined via a helper
script 'with-mailpile-env' that probes and constructs an environment
prioritizing mailpile's packaged dependencies. The script contains a hard-coded
set of dependencies to resolve, starting from the script's physical location.
Python libraries are injected into the PYTHONPATH environment variable, and
binaries are pre-pended to the system path.

Using the above strategy, tor, gpg, python, and gui-o-matic are made available.

A launch-mailpile script is also provided to invoke the above script to start
mailpile-gui.py. The intent is to provide a simple/intuitive high-level entry
point.

All mailpile dependencies run in the above environment unless otherwise specified.

## Modifying the packaging process ##

Modifying packaging convers a very wide range of subjects:

  - Specifying dependency sources (a.k.a. resources)
  - Modifying the build system to include new dependencies
  - Including new dependencies in packages
  - ...probably other things I'm forgetting right now

This reflects the internal flow in the build system: build scripts interact
with resources to prepare an install enviornment(somewhat akin to a fakeroot),
which is then rolled into a package. Resources and package layout are largely
described via configuration jsons, where as build steps are largely scripted.

### Specifying dependencies sources (a.k.a. resources) ###

Resources cover anything that needs to be downloaded and manipulated to produce
the package. Resources are specified as a json dictionary where each entry is
a dependency name with a url and sha1 sub-entry:

```json

{
  "<dependency name>": {"url": "<url string>", "sha1": "<sha1 digest of file>"}
}

```

The `provide/cache.py` utility is helpful for constructing and/or manipulating
resources files. See help for the utility for more info. Note that resources
can only be single files.

Internally the build system uses dependency names to interact with resources.
As long as the rest of the build steps are uneffected, it's possible to change
resource sources (i.e. version of python, tor, etc.) opaquely at this level.

See 'Producing a package' above for how to use a custom resource json in the
build system.

### Modifying the build system to include new dependencies ###

The build system is based off of lazily evaluating dependent scripts to produce
build artifacts. The artifacts need not be a package--the framework is flexible
enough to produce any intermediary. The build system is primarily organized
around decorating build scripts, which are later invoked around a build
context to help incrementally construct build artifacts. As part of the
build process, build scripts can also publish helper functions which can be
invoked by other scripts. In that sense, the build system simultaneously 
bootstraps itself and the build artifacts.

The auto-bootstrapping nature is increadibly useful for having a polite build
system: rather than requring the machine to be statically configured for
building, the build system incrementally assembles it's own dependencies on an
as-needed basis. In that sense, the build system does not distinguish between
it's own dependencies and those of the output artifact--both are assembled as
needed.

The build system has three customization points:

  - Build scripts to provide new dependencies
  - configuration points to easily change run time
  - default configuration functions

#### Build Scripts ####

Each dependency is associated with a build script, which is responsible for
completely configuring the dependency and returning a 'built' path for that
dependency:

```python

# Register this build script as a provider of multiple dependencies
#
def bind( framework ):
    '''
    bind the script to a build framework--maybe we'll need multiple build
    recipies at some point.
    '''
    
    @framework.provide('dependency1', 'dependency2')
    def provide_example(build, keyword):
        '''
        Build script example

        :build: build context
        :keyword: dependency name we're being asked to build
        :dep_path: suggested output path in the build directory
        '''

        # Depend on another build script's output
        # (and optionally get the path to that output)
        #
        external_dep = build.depend('external_dep')

        # 'root'--the build root, is a _very_ common depenendency. It also
        # publishes the 'path' command that can be used to discover output
        # paths for build products.
        #
        build.require('root')

        # use a function provided by another build script
        #
        dep_path = build.invoke('path', keyword)
        build.invoke('function_from_external_dep', dep_path)

        # provide a function for other build scripts
        #
        def example_function(*args, **kwargs):
            # Log events using standard python logging semantics
            #
            build.log().debug("called with {} {}".format(args, kwargs))

        build.publish(keyword + '_func', example_function) 

        # Return the path to the built dependency.
        # Return None if there are no resultant artifacts(i.e. just publishing)
        #
        return dep_path
```

There are already build scripts to handle several general cases:

  - Unpacking a zip
  - Checking out a git repository

These generic scripts can be extended to cover other dependencies by expanding
their registration:

```python

def bind(framework):

    # ... #
    @framework.provide('dependency1', 'dependency2', 'my_new_dependency')
    def function body(build, keyword):
        # ... #
```

There are also examples for working with MSIs and exes.

#### Configuration points ####

The build system exposes configuration to build scripts as a generic key-value
store. Configuration consolidates two configuration streams: a default
configuration method(see below), and user-defined override. Should neither
exist, the configuration system throws a KeyError, just like any other
key-value store. Build scripts can query configuration via the build context:

```python

def bind(framework):

    @framework.provide('example_dep')
    def provide_config_example(build, keyword):

        try:
            value = build.config('example-key')
        except KeyError:
            value = {'default': ['to','some','definition']}

        # ....

```

#### Default configuation ####

Rather than baking defaults into build scripts, it's better to explicity expose
them via the build system so that users can intuitively discover and manipulate
them. Default configurations are just functions that the build system invokes
to produce a value. They are registered via decorator, just like build scripts:

```python

def bind(framework):

    @framework.default_config('repo_a', 'repo_b')
    def config_repo_defaults(keyword):
        '''
        Provide the default url and commit to checkout for a repo
        '''
        return {'url': 'https://github.com/ExampleAccount/{}'.format(keyword),
                'commit': 'master' }


```


### Including new dependencies in packages ###

Packaging is actually just a build script that prepares an MSI via wix. It uses
a template 'package_template.json' that describes build elements to scan/import.
See the template for examples.

Note that the template uses brace expansion '{dependency}' to inject dependency
paths into the configuration.
