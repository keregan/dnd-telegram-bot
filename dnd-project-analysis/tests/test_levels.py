import unittest

from app.levels import get_level_info


class LevelTests(unittest.TestCase):
    def test_level_boundaries(self):
        self.assertEqual(get_level_info(-10)['level'], 1)
        self.assertEqual(get_level_info(299)['level'], 1)
        self.assertEqual(get_level_info(300)['level'], 2)
        self.assertEqual(get_level_info(355_000)['level'], 20)


if __name__ == '__main__':
    unittest.main()
