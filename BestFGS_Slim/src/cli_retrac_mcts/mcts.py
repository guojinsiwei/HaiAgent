"""Compatibility imports for experiments created before the BestFGS cleanup.

The online UCB/MCTS implementation was removed.  New code should import
``SearchConfig`` and related lifecycle types from :mod:`search_core`.
"""

from .search_core import (
    GraphSearchCore,
    PolicyModel,
    RewardConfig,
    SearchConfig,
    SearchResult,
    adapt_search_budget,
)

# Keep old configuration imports usable without carrying the old algorithm.
MCTSConfig = SearchConfig

__all__ = [
    "GraphSearchCore",
    "MCTSConfig",
    "PolicyModel",
    "RewardConfig",
    "SearchConfig",
    "SearchResult",
    "adapt_search_budget",
]
