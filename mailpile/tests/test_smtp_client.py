import unittest
import os
import mailpile
import random, string

from nose.tools import raises
from mailpile.tests import MailPileUnittest

def randomword(length):
    return ''.join(random.choice(string.lowercase) for i in range(length))

class TestConfig(MailPileUnittest):
    
    def test_sha512_512k(self): # the sha512_512k function always gives out a 128 length string    
        length = random.randint(1, 100)
        random_string = randomword(length)
        res = mailpile.smtp_client.sha512_512k(random_string)
        self.assertEqual(len(res), 128)
        
    def test_sha512_512kCheck(self):
        bits = random.randint(1, 100)
        length = random.randint(1, 10)
        random_challenge = randomword(length)
        random_solution = randomword(length)
        res = mailpile.smtp_client.sha512_512kCheck(random_challenge, bits, random_solution)
        self.assertEqual(res, False)