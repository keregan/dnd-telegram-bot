import unittest

from app.gameplay import format_roll, roll_dice


class FixedRandom:
    def __init__(self, values):
        self.values = iter(values)

    def randint(self, start, end):
        value = next(self.values)
        if not start <= value <= end:
            raise AssertionError('Fixed roll is outside requested bounds')
        return value


class GameplayTests(unittest.TestCase):
    def test_regular_roll(self):
        result = roll_dice('2d6+3', FixedRandom([2, 5]))
        self.assertEqual(result['total'], 10)
        self.assertIn('2, 5', format_roll(result))

    def test_advantage_and_disadvantage(self):
        advantage = roll_dice('adv+4', FixedRandom([3, 17]))
        disadvantage = roll_dice('dis-2', FixedRandom([8, 12]))
        self.assertEqual(advantage['total'], 21)
        self.assertEqual(disadvantage['total'], 6)

    def test_invalid_or_excessive_rolls_are_rejected(self):
        for expression in ('', '101d6', 'd1', 'hello', 'adv+1001'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                roll_dice(expression)


if __name__ == '__main__':
    unittest.main()
