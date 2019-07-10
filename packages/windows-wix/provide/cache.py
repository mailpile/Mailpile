from __future__ import print_function
import os.path
try:
    import urllib2
except ImportError:
    import urllib.request as urllib2
import logging
import hashlib
import tempfile
import datetime
import json
import ssl

logger = logging.getLogger(__name__)


class Cache(object):
    '''
    Cache for various file access methods. Only use default python packages to
    allow bootstrapping.
    '''

    @staticmethod
    def chunk_stream(src_read, dst_write, chunk_size=4096):
        while True:
            chunk = src_read(chunk_size)
            if len(chunk):
                dst_write(chunk)
            else:
                break

    @staticmethod
    def default_cache_dir():
        package = os.path.dirname(__file__)
        parent = os.path.abspath(os.path.dirname(package))
        return os.path.join(parent, 'download_cache')

    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir or self.default_cache_dir()
        if not os.path.isdir(self.cache_dir):
            logger.info("Creating cache directory '{}'".format(self.cache_dir))
            os.mkdir(self.cache_dir)

    @classmethod
    def download(cls, url, writer, **kwargs):
        logger.debug("Downloading '{}'...".format(url))
        context = ssl.create_default_context()
        try:
            try:
                source = urllib2.urlopen(url, context=context)
            except urllib2.URLError as e:
                if "CERTIFICATE_VERIFY_FAILED" in str(e):
                    logger.warning(
                        "Cannot verify ssl cert for '{}', delegating authenticity to digest...".format(url))
                    context = ssl._create_unverified_context()
                    source = urllib2.urlopen(url, context=context)
                else:
                    raise
            cls.chunk_stream(source.read, writer, **kwargs)
        except:
            logging.exception("Failed to fetch URL {}".format(url))
            raise

    @classmethod
    def sha1_handle(cls, handle, **kwargs):
        algo = hashlib.sha1()
        cls.chunk_stream(handle.read, algo.update, **kwargs)
        return algo.hexdigest().lower()

    @classmethod
    def sha1_file(cls, target, **kwargs):
        with open(target, 'rb') as handle:
            return cls.sha1_handle(handle, **kwargs)

    def __paths_for(self, url, sha1):
        dst_dir = os.path.join(self.cache_dir, sha1)
        dst_file = os.path.join(dst_dir, os.path.basename(url))
        dst_meta = os.path.join(dst_dir, "metadata.json")
        return (dst_dir, dst_file, dst_meta)

    def __cache_handle(self, url, sha1, handle, **kwargs):
        (dst_dir, dst_file, dst_meta) = self.__paths_for(url, digest)
        os.mkdir(dst_dir)

        with open(dst_file, 'wb') as dst_handle:
            self.chunk_stream(handle.read, dst_handle.write, **kwargs)

        metadata = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "url": url,
            "sha1": sha1,
            "filename": os.path.basename(dst_file)
        }
        with open(dst_meta, 'w') as handle:
            json.dump(metadata, handle)

        return (dst_file, digest)

    def __fetch(self, url, sha1, **kwargs):
        logger.debug("attempting to cache {} at {}".format(sha1, url))
        with tempfile.TemporaryFile() as temp:
            self.download(url, temp.write, **kwargs)
            temp.seek(0)
            digest = self.sha1_handle(temp)
            if sha1 is not None and sha1 != digest.lower():
                raise ValueError(
                    "Mismatched digest: {} {} for url '{}'".format(sha1, digest, url))

            temp.seek(0)

            (dst_dir, dst_file, dst_meta) = self.__paths_for(url, digest)
            os.mkdir(dst_dir)

            with open(dst_file, 'wb') as handle:
                self.chunk_stream(temp.read, handle.write, **kwargs)

            metadata = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "url": url,
                "sha1": sha1,
                "filename": os.path.basename(dst_file)
            }
            with open(dst_meta, 'w') as handle:
                json.dump(metadata, handle)

            return (dst_file, digest)

    def __open(self, url, sha1, **kwargs):
        logger.debug("inspecting cache for {} from {}".format(sha1, url))
        (dst_dir, dst_file, dst_meta) = self.__paths_for(url, sha1)

        with open(dst_meta, 'r') as handle:
            metadata = json.load(handle)

        cached_file = os.path.join(dst_dir, metadata['filename'])
        if cached_file != dst_file:
            logger.warn(
                "Cached filename {} doesn't match {}".format(cached_file, url))
        if metadata['url'] != url:
            logger.warn("Cached file from different url '{}' != '{}'".format(
                url, metadata['url']))

        logger.info("Using cached file '{}' with sha1 '{}' for url '{}'".format(
            cached_file, sha1, url))
        return cached_file

    def resolve(self, url, sha1, **kwargs):
        try:
            return self.__open(url, sha1, **kwargs)
        except IOError:
            logger.info("Url {}  is not cached.".format(url))
            return self.__fetch(url, sha1)[0]

    def insert(self, url, **kwargs):
        return self.__fetch(url, None, **kwargs)


class SemanticCache(object):
    '''
    Operates at a resource-level of abstraction on top of a regular cache
    '''

    def __init__(self, resources, cache=None):
        '''
        Create semantic cache with the specified resource dictionary.
        '''
        self.resources = resources
        self.cache = cache or Cache()

    def resource(self, name):
        '''
        Get the path to a resource by name, fetching it if neccessary.
        '''
        entry = self.resources[name]
        return self.cache.resolve(url = entry['url'], sha1 = entry['sha1'])

    def insert(self, key, url, comment = None):
        '''
        insert a resource--hash is computed on insert.
        '''
        path, sha1 = self.cache.insert(url)
        entry = {'url': url, 'sha1': sha1}
        if comment:
            entry['comment'] = comment
        try:
            self.resources[key].update(entry)
        except KeyError:
            self.resources[key] = entry
        self.resources[key] = {'url': url, 'sha1': sha1}

    def save(self, path, indent=2):
        '''
        save to json
        '''
        with open(path, 'w') as handle:
            json.dump(self.resources, handle, indent=indent)

    def preload(self):
        '''
        preload all resources.
        '''
        for key in self.resources.key():
            self.resource(key)

    @classmethod
    def load(cls, path, cache=None):
        '''
        create a new semantic cache from the specified path
        '''
        with open(path, 'r') as handle:
            return cls(json.load(handle), cache)


if __name__ == '__main__':
    logging.basicConfig()
    import argparse

    parser = argparse.ArgumentParser('Download cache')
    parser.add_argument('-c', '--cache', type=str, help="Cache location")
    parser.add_argument('json', type=str, help="Json of urls to cache")
    parser.add_argument('-r', '--resource', type=str, help="file to lookup")
    parser.add_argument('-l', '--log-level', type=str, help="logging level")
    parser.add_argument('-i', '--insert', type=str,
                        help='url to insert as ["key", "url", "comment"]')
    parser.add_argument('-a', '--all', action='store_true',
                        help='fetch all resources')
    args = parser.parse_args()

    if args.log_level:
        logger.setLevel(getattr(logging, args.log_level))

    cache = SemanticCache.load(args.json, Cache(args.cache))

    if args.insert:
        cache.insert(*json.loads(args.insert))
        cache.save(args.json)

    if args.resource:
        print(cache.resource(args.resource))

    if args.all:
        cache.preload()
