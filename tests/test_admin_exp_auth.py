import unittest

from npps4.system.admin_exp import is_loopback_address, verify_admin_exp_token


class AdminExpAuthorizationTests(unittest.TestCase):
    def test_ipv4_and_ipv6_loopback_are_allowed(self):
        self.assertTrue(is_loopback_address("127.0.0.1"))
        self.assertTrue(is_loopback_address("::1"))

    def test_non_loopback_and_invalid_hosts_are_rejected(self):
        for host in ("0.0.0.0", "192.168.1.10", "localhost", "", None):
            with self.subTest(host=host):
                self.assertFalse(is_loopback_address(host))

    def test_exact_bearer_token_is_required(self):
        self.assertTrue(verify_admin_exp_token("secret-token", "Bearer secret-token"))
        self.assertTrue(verify_admin_exp_token("secret-token", "bearer secret-token"))

    def test_missing_or_invalid_authorization_is_rejected(self):
        for header in (None, "", "secret-token", "Basic secret-token", "Bearer wrong", "Bearer secret-token "):
            with self.subTest(header=header):
                self.assertFalse(verify_admin_exp_token("secret-token", header))

    def test_missing_server_token_disables_authorization(self):
        self.assertFalse(verify_admin_exp_token(None, "Bearer secret-token"))
        self.assertFalse(verify_admin_exp_token("", "Bearer secret-token"))


if __name__ == "__main__":
    unittest.main()
