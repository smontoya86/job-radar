"""Job collectors for various sources."""
from .adzuna_collector import AdzunaCollector
from .ashby_collector import AshbyCollector
from .base import BaseCollector, JobData
from .greenhouse_collector import GreenhouseCollector
from .hn_collector import HNCollector
from .jsearch_collector import JSearchCollector
from .lever_collector import LeverCollector
from .remoteok_collector import RemoteOKCollector
from .search_discovery_collector import SearchDiscoveryCollector
from .serpapi_collector import SerpApiCollector
from .smartrecruiters_collector import SmartRecruitersCollector
from .workday_collector import WorkdayCollector

__all__ = [
    "BaseCollector",
    "JobData",
    "RemoteOKCollector",
    "AdzunaCollector",
    "GreenhouseCollector",
    "LeverCollector",
    "HNCollector",
    "AshbyCollector",
    "SerpApiCollector",
    "JSearchCollector",
    "WorkdayCollector",
    "SmartRecruitersCollector",
    "SearchDiscoveryCollector",
]
