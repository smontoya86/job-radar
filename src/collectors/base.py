"""Base collector interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class JobData:
    """Standardized job data structure from collectors."""

    title: str
    company: str
    url: str
    source: str
    location: Optional[str] = None
    description: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    apply_url: Optional[str] = None
    remote: bool = False
    posted_date: Optional[datetime] = None
    extra_data: dict = field(default_factory=dict)

    def __post_init__(self):
        """Normalize fields after initialization."""
        # Normalize remote detection from location
        if self.location:
            location_lower = self.location.lower()
            if any(term in location_lower for term in ["remote", "anywhere", "worldwide"]):
                self.remote = True


class BaseCollector(ABC):
    """Abstract base class for job collectors."""

    name: str = "base"

    @abstractmethod
    async def collect(self, search_queries: list[str]) -> list[JobData]:
        """
        Collect jobs matching the search queries.

        Args:
            search_queries: List of search terms/job titles to search for.

        Returns:
            List of JobData objects.
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
