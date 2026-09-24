import tempfile
import unittest
from pathlib import Path

from app.database import Database
from app.healthcheck import check_database


class HealthcheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_healthcheck_accepts_initialized_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / 'health.sqlite3')
            await Database(path).init()
            healthy, message = check_database(path)
            self.assertTrue(healthy)
            self.assertEqual(message, 'ok')

    async def test_healthcheck_rejects_missing_database(self):
        healthy, message = check_database('/tmp/database-that-does-not-exist.sqlite3')
        self.assertFalse(healthy)
        self.assertIn('missing', message)


if __name__ == '__main__':
    unittest.main()
