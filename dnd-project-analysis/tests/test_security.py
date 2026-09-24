import unittest

from app.security import create_password_hash, verify_password


class PasswordSecurityTests(unittest.TestCase):
    def test_password_hash_uses_unique_salt_and_verifies(self):
        first_salt, first_hash = create_password_hash('correct horse')
        second_salt, second_hash = create_password_hash('correct horse')

        self.assertNotEqual(first_salt, second_salt)
        self.assertNotEqual(first_hash, second_hash)
        self.assertTrue(verify_password('correct horse', first_salt, first_hash))
        self.assertFalse(verify_password('wrong password', first_salt, first_hash))


if __name__ == '__main__':
    unittest.main()
