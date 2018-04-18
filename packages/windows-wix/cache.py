import os.path
import urllib2
import logging
import hashlib
import tempfile
import datetime
import json

logger = logging.getLogger( __name__ )

class Cache( object ):
    '''
    Cache for various file access methods. Only use default python packages to
    allow bootstrapping.
    '''

    @staticmethod
    def chunk_stream( src_read, dst_write, chunk_size = 4096 ):
        while True:
            chunk = src_read( chunk_size )
            if len( chunk ):
                dst_write( chunk )
            else:
                break

    @staticmethod
    def default_cache_dir():
        parent = os.path.abspath( os.path.dirname( __file__ ) )
        return os.path.join( parent, 'download_cache' )

    def __init__( self, cache_dir = None ):
        self.cache_dir = cache_dir or self.default_cache_dir()
        if not os.path.isdir( self.cache_dir ):
            logger.info( "Creating cache directory '{}'".format( self.cache_dir ) )
            os.mkdir( self.cache_dir )

    @classmethod
    def download( cls, url, writer, **kwargs ):
        logger.debug( "Downloading '{}'...".format( url ) )
        try:
            source = urllib2.urlopen(url)
            cls.chunk_stream( source.read, writer, **kwargs )
                    
        except :
              logging.exception( "Failed to fetch URL {}".format( url ) )
              raise
            
    @classmethod
    def sha1_handle( cls, handle, **kwargs ):
        algo = hashlib.sha1()
        cls.chunk_stream( handle.read, algo.update, **kwargs )
        return algo.hexdigest().lower()
    
    @classmethod
    def sha1_file( cls, target, **kwargs ):
        with open( target, 'rb' ) as handle:
            return cls.sha1_handle( handle, **kwargs )

    def __paths_for( self, url, sha1 ):
        dst_dir = os.path.join( self.cache_dir, sha1 )
        dst_file = os.path.join( dst_dir, os.path.basename( url ) )
        dst_meta = os.path.join( dst_dir, "metadata.json" )
        return (dst_dir, dst_file, dst_meta)

    def __fetch( self, url, sha1, **kwargs ):
        logger.debug( "attempting to cache {} at {}".format( sha1, url ) )
        with tempfile.TemporaryFile() as temp:
            self.download( url, temp.write, **kwargs )
            temp.seek( 0 )
            digest = self.sha1_handle( temp )
            if sha1 != digest.lower():
                raise ValueError( "Mismatched digest: {} {} for url '{}'".format( sha1, digest, url ) )

            (dst_dir, dst_file, dst_meta) = self.__paths_for( url, sha1 )
            os.mkdir( dst_dir )
            
            temp.seek( 0 )
            with open( dst_file, 'wb' ) as handle:
                self.chunk_stream( temp.read, handle.write, **kwargs )

            metadata = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "url": url,
                "sha1": sha1,
                "filename": os.path.basename( dst_file )
            }
            with open( dst_meta, 'w' ) as handle:
                json.dump( metadata, handle )

            return dst_file

    def __open( self, url, sha1, **kwargs ):
        logger.debug( "inspecting cache for {} from {}".format( sha1, url ) )
        (dst_dir, dst_file, dst_meta) = self.__paths_for( url, sha1 )

        with open( dst_meta, 'r' ) as handle:
            metadata = json.load( handle )

        cached_file = os.path.join( dst_dir, metadata['filename'] )
        if cached_file != dst_file:
            logger.warn( "Cached filename {} doesn't match {}".format( cached_file, url ) )
        if metadata['url'] != url:
            logger.warn( "Cached file from different url '{}' != '{}'".format( url, metadata['url'] ) )

        logger.info( "Using cached file '{}' with sha1 '{}' for url '{}'".format( cached_file, sha1, url ) )
        return cached_file
    
    def resolve( self, url, sha1, **kwargs ):
        try:
            return self.__open( url, sha1, **kwargs )
        except IOError:
            logger.info( "Url {}  is not cached.".format( url ) )
            return self.__fetch( url, sha1 )

if __name__ == '__main__':
    logging.basicConfig()
    logger.setLevel( logging.DEBUG )
    cache = Cache()
    print cache.resolve( 'https://www.python.org/ftp/python/2.7.14/python-2.7.14.msi', 'a84cb11bdae3e1cb76cf45aa96838d80b9dcd160' )
