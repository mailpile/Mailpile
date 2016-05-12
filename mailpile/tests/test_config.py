import unittest
import os
import mailpile
import mailpile.config.validators as validators

from nose.tools import raises
from mailpile.tests import MailPileUnittest


class TestConfig(MailPileUnittest):

    #
    # config._BoolCheck should convert common yes/no strings into boolean values
    #
    def test_BoolCheck_trues(self):
        for t in ["yes", "true", "on", "1", True]:
            res = validators.BoolCheck(t)
            self.assertEqual(res, True)

    def test_BoolCheck_falses(self):
        for f in ["no", "false", "off", "0", False]:
            res = validators.BoolCheck(f)
            self.assertEqual(res, False)

    def test_BoolCheck_exception(self):
        for ex in ["wiggle", ""]:
            self.assertRaises(ValueError, lambda: validators.BoolCheck(ex))

    #
    # config._RouteProtocolCheck should verify that the protocol is actually a protocol, and strip and lowercase it
    #
    def test_RouteProtocolCheck_valid(self):
        valid_protos = [
            ["SMTP", "smtp"],
            ["smtptls ", "smtptls" ],
            ["smtpSSL", "smtpssl"],
            [" local ", "local"]
        ]
        for v in valid_protos:
            res = validators.RouteProtocolCheck(v[0])
            self.assertEqual(res, v[1])

    def test_RouteProtocolCheck_invalid(self):
        invalid_protos = ["http", "scp", "ssh", "spam"]
        for i in invalid_protos:
            self.assertRaises(ValueError, lambda: validators.RouteProtocolCheck(i))

    #
    # config._HostNameValid should verify that a string is a valid hostname, returning a bool
    #
    def test_HostNameValid_ipv4(self):
        ipv4_addrs = [
          "127.0.0.1",
          "172.16.254.180"
        ]
        for ipv4 in ipv4_addrs:
            res = validators.HostNameValid(ipv4)
            self.assertEqual(res, True)

    def test_HostNameValid_ipv6(self):
        ipv6_addrs = [
          "2001:cdba::3257:9651",
          "ff02::9",
          "::1"
        ]
        for ipv6 in ipv6_addrs:
            res = validators.HostNameValid(ipv6)
            self.assertEqual(res, True)

    def test_HostNameValid_hostname(self):
        hostnames = [
          "localhost",
          "foo.bar",
          "eggs.foo.br",
          "spam.eggs.foo.bar"
        ]
        for hname in hostnames:
            res = validators.HostNameValid(hname)
            self.assertEqual(res, True)


    #
    # config._HostNameCheck should verify that a string is a valid hostname
    #
    def test_HostNameCheck_valid(self):
        valids = [
          "127.0.0.1",
          "localhost",
          "ff02::9"
        ]
        for v in valids:
            res = validators.HostNameCheck(v)
            self.assertEqual(res, v)

    def test_HostNameCheck_invalid(self):
        invalid_hostnames = [
          "",
          " ",
          "127.0.0.17889",
          "12.2",
          "my.9",
          "25:25:16",
          "hello.com?q=45",
          " a ",
          " mysite.com",
          "20.20.280.1",
          "8.999.89.11.23.34",
          "/some/path",
          "asdf::/12"
        ]
        for invalid in invalid_hostnames:
            self.assertRaises(ValueError, lambda: validators.HostNameCheck(invalid))

    def test_HostNameCheck_non_socket_errors_still_raised(self):
        self.assertRaises(NameError, lambda: validators.HostNameCheck(asdf))

    #
    # config._SlugCheck should verify that a string is a valid url slug
    #
    def test_SlugCheck_valid(self):
        valid_slugs = ["_Foo-bar.7", "foobar", "spam-eggs", "_"]
        for v in valid_slugs:
            res = validators.SlugCheck(v)
            self.assertEqual(res, v.lower())

    def test_SlugCheck_invalid(self):
        invalid_slugs = ["url/path", "Bad Slug"]
        for nv in invalid_slugs:
            self.assertRaises(ValueError, lambda: validators.SlugCheck(nv))

    #
    # config._SlashSlugCheck should act like _SlugCheck bug allow slashes
    #
    def test_SlashSlugCheck(self):
        valids = ["some/path", "a/very/long/path"]
        for v in valids:
            res = validators.SlashSlugCheck(v)
            self.assertEqual(res, v.lower())

    #
    # config._B36Check should verify that a string is a valid base-36 integer
    #
    def test_B36Check(self):
        valids = ["aa", "10","AA"]
        for v in valids:
            res = validators.B36Check(v)
            self.assertEqual(res, v.lower())

    def test_B36Check(self):
        invalids = ["=", ".", "~12", "1278@"]
        for i in invalids:
            self.assertRaises(ValueError, lambda: validators.B36Check(i))

    #
    # config._PathCheck should verify that a string is a valid and existing path and make it absolute
    # skipped for windows (should be added later)
    #

    @unittest.skipIf(os.name == 'nt', "testing skipped in windows")
    def test_PathCheck_valid(self):
        valid_paths = {
          "posix" : [
            ["/etc/../", "/"]
          ]
        }
        for v in valid_paths[os.name]:
            res = validators.PathCheck(v[0])
            self.assertEqual(res, v[1])

    @unittest.skipIf(os.name == 'nt', "testing skipped in windows")
    def test_PathCheck_invalid(self):
        invalid_paths = {
          "posix" : ["/asdf/asdf/asdf", ""]
        }
        for i in invalid_paths[os.name]:
            self.assertRaises(ValueError, lambda: validators.PathCheck(i))

    #
    # config._FileCheck should verify that a string is an existing file and make it absolute
    # skipped for windows (should be added later)
    #

    @unittest.skipIf(os.name == 'nt', "testing skipped in windows")
    def test_FileCheck_valid(self):
      valid_paths = {
        "posix" : [
          ["/etc/../etc/group", "/etc/group" ]
        ]
      }
      for v in valid_paths[os.name]:
          res = validators.FileCheck(v[0])
          self.assertEqual(res, v[1])

    @unittest.skipIf(os.name == 'nt', "testing skipped in windows")
    def test_FileCheck_invalid(self):
        invalid_paths = {
          "posix" : ["/etc", "/", "", "laksh09hahs--x"]
        }
        for i in invalid_paths[os.name]:
            self.assertRaises(ValueError, lambda: validators.FileCheck(i))

    #
    # config._DirCheck should verify that a string is an existing directory and make it absolute
    # skipped for windows (should be added later)
    #

    @unittest.skipIf(os.name == 'nt', "testing skipped in windows")
    def test_DirCheck_valid(self):
        valid_paths = {
          "posix" : [
            ["/etc/../", "/"]
          ]
        }
        for v in valid_paths[os.name]:
            res = validators.DirCheck(v[0])
            self.assertEqual(res, v[1])

    @unittest.skipIf(os.name == 'nt', "testing skipped in windows")
    def test_DirCheck_invalid(self):
        invalid_paths = {
          "posix" : [ "/etc/group", "" ]
        }
        for i in invalid_paths[os.name]:
            self.assertRaises(ValueError, lambda: validators.DirCheck(i))

    #
    # config._NewPathCheck should verify that a string is path to an existing directory and make it absolute
    # skipped for windows (should be added later)
    #

    @unittest.skipIf(os.name == 'nt', "testing skipped in windows")
    def test_NewPathCheck_valid(self):
        valid_paths = {
          "posix" : [
            ["/etc/temp.txt", "/etc/temp.txt"],
            ["/etc/../magic", "/magic"]
          ]
        }
        for v in valid_paths[os.name]:
            res = validators.NewPathCheck(v[0])
            self.assertEqual(res, v[1])

    @unittest.skipIf(os.name == 'nt', "testing skipped in windows")
    def test_NewPathCheck_invalid(self):
        invalid_paths = {
          "posix" : [ "/some/random/path/", "/etc/asdf/tmp.txt" ]
        }
        for i in invalid_paths[os.name]:
            self.assertRaises(ValueError, lambda: validators.NewPathCheck(i))

    #
    # config._UrlCheck should verify that a string is a valid url
    #
    def test_UrlCheck_valid(self):
        valid_urls = [
          "http://site.io",
          "https://localhost",
          "git://github.com/user/repo.git",
          "magnet:?xt=urn:sha1:1C6HTVCWBTRNJ9V4XNAE52SJUQCZO5D",
        ]
        for v in valid_urls:
            res = validators.UrlCheck(v)
            self.assertEqual(res, v)

    def test_UrlCheck_invalid(self):
        invalid_urls = [
          "obvious",
          "",
          " ",
          ".com",
          "/just/a/path",
        ]
        for i in invalid_urls:
            self.assertRaises(ValueError, lambda: validators.UrlCheck(i))

    #
    #config._EmailCheck should verify that an email address has an @ symbol
    #
    def test_EmailCheck_valid(self):
        valid_emails = [
          '"This is a valid email!"@believe.it',
          'this.address(has-a-comment)@crazy-but-true.com',
          '"ABC\@def"@valid-email.com',
          '\$A12345@valid-email.com',
          '!def!xyz%abc@valid-email.com',
          '_somename@valid-email.com',
          '"Some\\Body"@valid-email.com'
        ]

        for v in valid_emails:
            res = validators.EmailCheck(v)
            self.assertEqual(res, v)

    def test_EmailCheck_invalid(self):
        invalid_emails = [
          "invalidEmail",
          "",
          "@invalid-email",
          "@"
        ]

        for i in invalid_emails:
            self.assertRaises(ValueError, lambda: validators.EmailCheck(i))

    def test_GPGKeyCheck_valid(self):
        valid_fingerprints = [
          'User@Foo.com',
          '1234 5678 abcd EF00',
          '12345678'
        ]

        res = validators.GPGKeyCheck(valid_fingerprints[0])
        self.assertEqual(res, 'User@Foo.com')

        res = validators.GPGKeyCheck(valid_fingerprints[1])
        self.assertEqual(res, '12345678ABCDEF00')

        res = validators.GPGKeyCheck(valid_fingerprints[2])
        self.assertEqual(res, '12345678')

    def test_GPGKeyCheck_invalid(self):
        invalid_fingerprints = [
          '123456789',                                             # length of key not 8 or 16 or 40
          'B906 8A28 15C4 F859  6F9F 47C1 3F3F ED73 5179',         # length is 36 i.e not 40
          'zzzz zzzz zzzz zzzz zzzz  zzzz zzzz zzzz zzzz zzzz' # contains invalid character z characters should be within a-f
        ]

        for i in invalid_fingerprints:
            self.assertRaises(ValueError, lambda: validators.GPGKeyCheck(i))
