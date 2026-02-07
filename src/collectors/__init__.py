"""Job collectors for various sources."""
from .adzuna_collector import AdzunaCollector
from .ashby_collector import AshbyCollector
from .base import BaseCollector, JobData
from .greenhouse_collector import GreenhouseCollector
from .himalayas_collector import HimalayasCollector
from .hn_collector import HNCollector
from .jsearch_collector import JSearchCollector
from .lever_collector import LeverCollector
from .remoteok_collector import RemoteOKCollector
from .remotive_collector import RemotiveCollector
from .search_discovery_collector import SearchDiscoveryCollector
from .serpapi_collector import SerpApiCollector
from .smartrecruiters_collector import SmartRecruitersCollector
from .themuse_collector import TheMuseCollector
from .workday_collector import WorkdayCollector

__all__ = [
    "BaseCollector",
    "JobData",
    "RemoteOKCollector",
    "RemotiveCollector",
    "AdzunaCollector",
    "GreenhouseCollector",
    "HimalayasCollector",
    "LeverCollector",
    "HNCollector",
    "AshbyCollector",
    "SerpApiCollector",
    "JSearchCollector",
    "WorkdayCollector",
    "SmartRecruitersCollector",
    "SearchDiscoveryCollector",
    "TheMuseCollector",
]
