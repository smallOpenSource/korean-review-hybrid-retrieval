"""Collector modules for various app stores."""

from .play_store_collector import PlayStoreCollector, ReviewData, get_play_store_collector

__all__ = [
    'PlayStoreCollector',
    'ReviewData',
    'get_play_store_collector',
]
