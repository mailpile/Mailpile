import unittest
import os
import mailpile

from nose.tools import raises
from mailpile.tests import MailPileUnittest

class TestConfig(MailPileUnittest):

    #
    # config._BoolCheck should convert common yes/no strings into boolean values
    #
    def test_BoolCheck_trues(self):
        for t in ["yes", "true", "on", "1", True]:
            res = mailpile.config._BoolCheck(t)
            self.assertEqual(res, True)

    def test_BoolCheck_falses(self):
        for f in ["no", "false", "off", "0", False]:
            res = mailpile.config._BoolCheck(f)
            self.assertEqual(res, False)

    def test_BoolCheck_exception(self):
        for ex in ["3", "wiggle", ""]:
            self.assertRaises(ValueError, lambda: mailpile.config._BoolCheck(ex))

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
            res = mailpile.config._RouteProtocolCheck(v[0])
            self.assertEqual(res, v[1])

    def test_RouteProtocolCheck_invalid(self):
        invalid_protos = ["http", "scp", "ssh", "spam"]
        for i in invalid_protos:
            self.assertRaises(ValueError, lambda: mailpile.config._RouteProtocolCheck(i))

    #
    # config._HostNameValid should verify that a string is a valid hostname, returning a bool
    #
    def test_HostNameValid_ipv4(self):
        ipv4_addrs = [
          "127.0.0.1",
          "172.16.254.180"
        ]
        for ipv4 in ipv4_addrs:
            res = mailpile.config._HostNameValid(ipv4)
            self.assertEqual(res, True)

    def test_HostNameValid_ipv6(self):
        ipv6_addrs = [
          "2001:cdba::3257:9651",
          "ff02::9",
          "::1"
        ]
        for ipv6 in ipv6_addrs:
            res = mailpile.config._HostNameValid(ipv6)
            self.assertEqual(res, True)

    def test_HostNameValid_hostname(self):
        hostnames = [
          "localhost",
          "foo.bar",
          "eggs.foo.br",
          "spam.eggs.foo.bar"
        ]
        for hname in hostnames: 
            res = mailpile.config._HostNameValid(hname)
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
            res = mailpile.config._HostNameCheck(v)
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
            self.assertRaises(ValueError, lambda: mailpile.config._HostNameCheck(invalid))

    def test_HostNameCheck_non_socket_errors_still_raised(self):
        self.assertRaises(NameError, lambda: mailpile.config._HostNameCheck(asdf)) 

    #
    # config._SlugCheck should verify that a string is a valid url slug
    #
    def test_SlugCheck_valid(self):
        valid_slugs = ["_Foo-bar.7", "foobar", "spam-eggs", "_"]
        for v in valid_slugs:
            res = mailpile.config._SlugCheck(v)
            self.assertEqual(res, v.lower())

    def test_SlugCheck_invalid(self):
        invalid_slugs = ["url/path", "Bad Slug"]
        for nv in invalid_slugs:
            self.assertRaises(ValueError, lambda: mailpile.config._SlugCheck(nv))

    #
    # config._SlashSlugCheck should act like _SlugCheck bug allow slashes 
    #
    def test_SlashSlugCheck(self):
        valids = ["some/path", "a/very/long/path"]
        for v in valids:
            res = mailpile.config._SlashSlugCheck(v)
            self.assertEqual(res, v.lower())

    #
    # config._B36Check should verify that a string is a valid base-36 integer
    #
    def test_B36Check(self):
        valids = ["aa", "10","AA"]
        for v in valids:
            res = mailpile.config._B36Check(v)
            self.assertEqual(res, v.lower())

    def test_B36Check(self):
        invalids = ["=", ".", "~12", "1278@"]
        for i in invalids:
            self.assertRaises(ValueError, lambda: mailpile.config._B36Check(i))

    #
    # config._PathCheck should verify that a string is a valid and existing path and make it absolute
    #

    def test_PathCheck_valid(self):
        valid_paths = {
          "posix" : [
            ["/etc/../", "/"]
          ]
        }
        for v in valid_paths[os.name]:
            res = mailpile.config._PathCheck(v[0])
            self.assertEqual(res, v[1])

    def test_PathCheck_invalid(self):
        invalid_paths = {
          "posix" : ["/asdf/asdf/asdf", ""]
        }
        for i in invalid_paths[os.name]:
            self.assertRaises(ValueError, lambda: mailpile.config._PathCheck(i))

    #
    # config._FileCheck should verify that a string is an existing file and make it absolute
    #
    def test_FileCheck_valid(self):
      valid_paths = {
        "posix" : [
          ["/etc/../etc/group", "/etc/group" ]
        ]
      }
      for v in valid_paths[os.name]:
          res = mailpile.config._FileCheck(v[0])
          self.assertEqual(res, v[1])

    def test_FileCheck_invalid(self):
        invalid_paths = {
          "posix" : ["/etc", "/", "", "laksh09hahs--x"]
        }
        for i in invalid_paths[os.name]:
            self.assertRaises(ValueError, lambda: mailpile.config._FileCheck(i))

    #
    # config._DirCheck should verify that a string is an existing directory and make it absolute
    #
    def test_DirCheck_valid(self):
        valid_paths = {
          "posix" : [
            ["/etc/../", "/"]
          ]
        }
        for v in valid_paths[os.name]:
            res = mailpile.config._DirCheck(v[0])
            self.assertEqual(res, v[1])

    def test_DirCheck_invalid(self):
        invalid_paths = {
          "posix" : [ "/etc/group", "" ]
        }
        for i in invalid_paths[os.name]:
            self.assertRaises(ValueError, lambda: mailpile.config._DirCheck(i))

    #
    # config._NewPathCheck should verify that a string is path to an existing directory and make it absolute
    #
    def test_NewPathCheck_valid(self):
        valid_paths = {
          "posix" : [
            ["/etc/temp.txt", "/etc/temp.txt"],
            ["/etc/../magic", "/magic"]
          ]
        }
        for v in valid_paths[os.name]:
            res = mailpile.config._NewPathCheck(v[0])
            self.assertEqual(res, v[1])

    def test_NewPathCheck_invalid(self):
        invalid_paths = {
          "posix" : [ "/some/random/path/", "/etc/asdf/tmp.txt" ]
        }
        for i in invalid_paths[os.name]:
            self.assertRaises(ValueError, lambda: mailpile.config._NewPathCheck(i))

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
            res = mailpile.config._UrlCheck(v)
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
            self.assertRaises(ValueError, lambda: mailpile.config._UrlCheck(i))

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
            res = mailpile.config._EmailCheck(v)
            self.assertEqual(res, v)

    def test_EmailCheck_invalid(self):
        invalid_emails = [
          "invalidEmail",
          "",
          "@invalid-email",
          "@"
        ]

        for i in invalid_emails:
            self.assertRaises(ValueError, lambda: mailpile.config._EmailCheck(i))
