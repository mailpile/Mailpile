import unittest
import os
from mock import patch

import mailpile
from mailpile.commands import Action as action
from mailpile.tests import MailPileUnittest


class TestCommands(MailPileUnittest):
    def test_index(self):
        res = self.mp.rescan()
        self.assertEqual(res.as_dict()["status"], 'success')

    def test_search(self):
        # A random search must return results in less than 0.2 seconds.
        res = self.mp.search("foo")
        self.assertLess(float(res.as_dict()["elapsed"]), 0.2)

    def test_optimize(self):
        res = self.mp.optimize()
        self.assertEqual(res.as_dict()["result"], True)

    def test_set(self):
        self.mp.set("prefs.num_results=1")
        results = self.mp.search("twitter")
        self.assertEqual(results.result['stats']['count'], 1)

    def test_unset(self):
        self.mp.unset("prefs.num_results")
        results = self.mp.search("twitter")
        self.assertEqual(results.result['stats']['count'], 3)

    def test_add(self):
        res = self.mp.add("scripts")
        self.assertEqual(res.as_dict()["result"], True)

    def test_add_mailbox_already_in_pile(self):
        res = self.mp.add("scripts")
        self.assertEqual(res.as_dict()["result"], True)

    def test_add_mailbox_no_such_directory(self):
        res = self.mp.add("wut?")
        self.assertEqual(res.as_dict()["result"], False)

    def test_output(self):
        res = self.mp.output("json")
        self.assertEqual(res.as_dict()["result"], {'output': 'json'})

    def test_help(self):
        res = self.mp.help()
        self.assertEqual(len(res.result), 3)

    def test_help_variables(self):
        res = self.mp.help_variables()
        self.assertGreater(len(res.result['variables']), 1)

    def test_help_with_param_search(self):
        res = self.mp.help('search')
        self.assertEqual(res.result['pre'], 'Search your mail!')

    def test_help_urlmap_as_text(self):
        res = self.mp.help_urlmap()
        self.assertEqual(len(res.result), 1)
        self.assertGreater(res.as_text(), 0)

    def test_crypto_policy_auto_set_all_action(self):
        res = self.mp.crypto_policy_auto_set_all()
        self.assertEqual(res.as_dict()["message"], u'Discovered crypto policy')
        self.assertEqual(set(), res.as_dict()['result'])

    def test_crypto_policy_action(self):
        res = self.mp.crypto_policy("foobar")
        self.assertEqual(res.as_dict()["message"], u'Crypto policy for foobar is none')
        self.assertEqual(res.as_dict()["result"], 'none')


class TestCommandResult(MailPileUnittest):
    def test_command_result_as_dict(self):
        res = self.mp.help_splash()
        self.assertGreater(len(res.as_dict()), 0)

    def test_command_result_as_text(self):
        res = self.mp.help_splash()
        self.assertGreater(res.as_text(), 0)

    def test_command_result_as_text_for_boolean_result(self):
        res = self.mp.rescan()
        self.assertEquals(res.result['messages'], 0)
        self.assertEquals(res.result['mailboxes'], 0)
        self.assertEquals(res.result['vcards'], 0)

    def test_command_result_non_zero(self):
        res = self.mp.help_splash()
        self.assertTrue(res)

    def test_command_result_as_json(self):
        res = self.mp.help_splash()
        self.assertGreater(res.as_json(), 0)

    def test_command_result_as_html(self):
        res = self.mp.help_splash()
        self.assertGreater(res.as_html(), 0)


class TestTagging(MailPileUnittest):
    def test_addtag(self):
        pass


class TestGPG(MailPileUnittest):
    def test_key_search(self):
        gpg_result = {
            "D13C70DA": {
                "uids": [
                    {
                        "email": "smari@mailpile.is"
                    }
                ]
            }
        }

        with patch('mailpile.commands.GnuPG') as gpg_mock:
            gpg_mock.return_value.search_key.return_value = gpg_result

            res = action(self.mp._session, "crypto/gpg/searchkey", "D13C70DA")
            email = res.result["D13C70DA"]["uids"][0]["email"]
            self.assertEqual(email, "smari@mailpile.is")
            gpg_mock.return_value.search_key.assert_called_with("D13C70DA")

    def test_key_receive(self):
        gpg_result = {
            "updated": [
                {
                    "fingerprint": "08A650B8E2CBC1B02297915DC65626EED13C70DA"
                }
            ]
        }

        with patch('mailpile.commands.GnuPG') as gpg_mock:
            gpg_mock.return_value.recv_key.return_value = gpg_result

            res = action(self.mp._session, "crypto/gpg/receivekey", "D13C70DA")
            self.assertEqual(res.result[0]["updated"][0]["fingerprint"],
                             "08A650B8E2CBC1B02297915DC65626EED13C70DA")
            gpg_mock.return_value.recv_key.assert_called_with("D13C70DA")

    def test_key_import(self):
        res = action(self.mp._session, "crypto/gpg/importkey",
                     os.path.join('mailpile', 'tests', 'data', 'pub.key'))
        self.assertEqual(res.result["results"]["count"], 1)

    def test_nicknym_get_key(self):
        pass

    def test_nicknym_refresh_key(self):
        pass


if __name__ == '__main__':
    unittest.main()
