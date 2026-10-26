import inspect
import unittest

from cli_retrac_mcts.mcts import (
    CoverageRewardCalculator,
    CoverageUCBInputs,
    MCTSConfig,
    coverage_guided_ucb,
)


class UCBTests(unittest.TestCase):
    def test_default_semantic_switch_threshold_is_slightly_lowered(self) -> None:
        self.assertEqual(MCTSConfig().semantic_coverage_switch_threshold, 0.48)

    def test_semantic_coverage_guides_selection(self) -> None:
        common = dict(
            parent_visits=10,
            edge_visits=2,
            edge_total_value=1.0,
            exploration_constant=1.0,
            parent_semantic_coverage_rate=0.0,
            semantic_coverage_weight=0.5,
            semantic_coverage_switch_threshold=0.6,
            recommend_rule_applied=False,
            recommend_rule_weight=0.5,
        )
        low = coverage_guided_ucb(CoverageUCBInputs(semantic_coverage_rate=0.2, **common))
        high = coverage_guided_ucb(CoverageUCBInputs(semantic_coverage_rate=0.8, **common))
        self.assertAlmostEqual(high - low, 0.3)

    def test_semantic_coverage_term_smoothly_reaches_zero_at_threshold(self) -> None:
        common = dict(
            parent_visits=10,
            edge_visits=2,
            edge_total_value=1.0,
            exploration_constant=0.0,
            semantic_coverage_weight=0.5,
            semantic_coverage_switch_threshold=0.6,
            recommend_rule_applied=False,
            recommend_rule_weight=0.5,
        )
        low_coverage = coverage_guided_ucb(
            CoverageUCBInputs(
                parent_semantic_coverage_rate=0.0,
                semantic_coverage_rate=0.8,
                **common,
            )
        )
        halfway = coverage_guided_ucb(
            CoverageUCBInputs(
                parent_semantic_coverage_rate=0.3,
                semantic_coverage_rate=0.8,
                **common,
            )
        )
        switched = coverage_guided_ucb(
            CoverageUCBInputs(
                parent_semantic_coverage_rate=0.6,
                semantic_coverage_rate=0.8,
                **common,
            )
        )
        self.assertAlmostEqual(low_coverage - halfway, 0.2)
        self.assertAlmostEqual(halfway - switched, 0.2)

    def test_traditional_exploration_term_uses_coverage_annealing(self) -> None:
        common = dict(
            parent_visits=10,
            edge_visits=2,
            edge_total_value=0.0,
            exploration_constant=1.0,
            semantic_coverage_rate=0.0,
            semantic_coverage_weight=0.0,
            semantic_coverage_switch_threshold=0.6,
            recommend_rule_applied=False,
            recommend_rule_weight=0.0,
        )
        early = coverage_guided_ucb(
            CoverageUCBInputs(parent_semantic_coverage_rate=0.0, **common)
        )
        halfway = coverage_guided_ucb(
            CoverageUCBInputs(parent_semantic_coverage_rate=0.3, **common)
        )
        switched = coverage_guided_ucb(
            CoverageUCBInputs(parent_semantic_coverage_rate=0.6, **common)
        )

        self.assertGreater(early, halfway)
        self.assertAlmostEqual(halfway, early * 0.5)
        self.assertEqual(switched, 0.0)

    def test_recommend_rule_term_decays_with_edge_visits(self) -> None:
        common = dict(
            parent_visits=15,
            edge_total_value=1.0,
            exploration_constant=1.0,
            parent_semantic_coverage_rate=0.6,
            semantic_coverage_rate=0.5,
            semantic_coverage_weight=0.5,
            semantic_coverage_switch_threshold=0.6,
            recommend_rule_weight=0.4,
        )
        plain_once = coverage_guided_ucb(
            CoverageUCBInputs(
                edge_visits=1,
                recommend_rule_applied=False,
                **common,
            )
        )
        recommended_once = coverage_guided_ucb(
            CoverageUCBInputs(
                edge_visits=1,
                recommend_rule_applied=True,
                **common,
            )
        )
        plain_three = coverage_guided_ucb(
            CoverageUCBInputs(
                edge_visits=3,
                recommend_rule_applied=False,
                **common,
            )
        )
        recommended_three = coverage_guided_ucb(
            CoverageUCBInputs(
                edge_visits=3,
                recommend_rule_applied=True,
                **common,
            )
        )
        first_bonus = recommended_once - plain_once
        later_bonus = recommended_three - plain_three
        self.assertAlmostEqual(first_bonus, 0.2)
        self.assertAlmostEqual(later_bonus, 0.1)

    def test_recommend_rule_weight_must_be_non_negative(self) -> None:
        with self.assertRaisesRegex(ValueError, "recommend_rule_weight"):
            MCTSConfig(recommend_rule_weight=-0.1).validate()

    def test_semantic_switch_threshold_must_be_a_rate(self) -> None:
        for invalid in (0.0, -0.1, 1.1):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    ValueError,
                    "semantic_coverage_switch_threshold",
                ):
                    MCTSConfig(
                        semantic_coverage_switch_threshold=invalid
                    ).validate()

    def test_post_hoc_indicators_do_not_leak_into_ucb_or_reward(self) -> None:
        source = inspect.getsource(coverage_guided_ucb) + inspect.getsource(
            CoverageRewardCalculator.calculate
        )
        for forbidden in (
            "effective_exploration_ratio",
            "knowledge_reuse_rate",
            "tool_call_redundancy_rate",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
