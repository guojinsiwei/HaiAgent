import unittest

from bestfgs.rl import GRPOBuffer, GRPOSample, clipped_surrogate


class GRPOTests(unittest.TestCase):
    def test_group_relative_advantages(self) -> None:
        buffer = GRPOBuffer(
            [
                GRPOSample("group", 1, "state", "a", "d", 0.0, 0.0, 0.0),
                GRPOSample("group", 2, "state", "b", "d", 2.0, 1.0, 1.0),
            ]
        )
        advantages = buffer.with_group_relative_advantages()
        self.assertAlmostEqual(advantages[0].advantage, -1.0)
        self.assertAlmostEqual(advantages[1].advantage, 1.0)

    def test_clipped_surrogate(self) -> None:
        self.assertAlmostEqual(
            clipped_surrogate(probability_ratio=1.5, advantage=1.0), 1.2
        )


if __name__ == "__main__":
    unittest.main()
