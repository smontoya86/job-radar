"""Job collectors for various sources."""
from .adzuna_collector import AdzunaCollector
from .base import BaseCollector, JobData
from .greenhouse_collector import GreenhouseCollector
from .hn_collector import HNCollector
from .jobspy_collector import JobSpyCollector
from .lever_collector import LeverCollector
from .remoteok_collector import RemoteOKCollector
from .wellfound_collector import WellfoundCollector

__all__ = [
    "BaseCollector",
    "JobData",
    "JobSpyCollector",
    "RemoteOKCollector",
    "AdzunaCollector",
    "GreenhouseCollector",
    "LeverCollector",
    "HNCollector",
    "WellfoundCollector",
]
