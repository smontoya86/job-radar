"""Keyword matching for job descriptions - Description-Centric Algorithm."""
import re
from dataclasses import dataclass, field
from typing import Optional

import yaml

from src.collectors.base import JobData


@dataclass
class MatchResult:
    """Result of keyword matching."""

    matched: bool
    score: float  # 0-100
    matched_primary: list[str] = field(default_factory=list)
    matched_secondary: list[str] = field(default_factory=list)
    matched_title: bool = False
    matched_company_tier: Optional[int] = None
    negative_matches: list[str] = field(default_factory=list)
    salary_match: bool = True
    remote_match: bool = True
    # New fields for description analysis
    description_keyword_count: int = 0  # Total keyword mentions in description
    description_keyword_variety: int = 0  # Unique keywords found in description
    title_partial_match: float = 0.0  # Partial title match score (0-1)


class KeywordMatcher:
    """Match jobs against profile keywords."""

    def __init__(self, profile_path: str):
        """
        Initialize keyword matcher with profile.

        Args:
            profile_path: Path to profile.yaml file
        """
        self.profile = self._load_profile(profile_path)
        self._compile_patterns()

    def _load_profile(self, path: str) -> dict:
        """Load profile from YAML file."""
        with open(path) as f:
            return yaml.safe_load(f)

    def _compile_patterns(self) -> None:
        """Compile regex patterns for keywords."""
        # Primary keywords (must have at least one)
        primary = self.profile.get("required_keywords", {}).get("primary", [])
        self.primary_patterns = [
            re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in primary
        ]
        self.primary_keywords = primary

        # Secondary keywords (bonus)
        secondary = self.profile.get("required_keywords", {}).get("secondary", [])
        self.secondary_patterns = [
            re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in secondary
        ]
        self.secondary_keywords = secondary

        # Negative keywords (exclude)
        negative = self.profile.get("negative_keywords", [])
        self.negative_patterns = [
            re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in negative
        ]
        self.negative_keywords = negative

        # Target titles
        primary_titles = self.profile.get("target_titles", {}).get("primary", [])
        secondary_titles = self.profile.get("target_titles", {}).get("secondary", [])
        self.all_target_titles = primary_titles + secondary_titles
        self.title_patterns = [
            re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)
            for t in self.all_target_titles
        ]

        # Precompute core role terms for title relevance scoring
        self.core_role_terms = self._extract_core_role_terms()

        # Target companies by tier
        self.company_tiers = {
            company.lower(): tier
            for tier in [1, 2, 3]
            for company in self.profile.get("target_companies", {}).get(f"tier{tier}", [])
        }

        # Compensation
        self.min_salary = self.profile.get("compensation", {}).get("min_salary", 0)
        self.max_salary = self.profile.get("compensation", {}).get("max_salary", 999999)
        self.salary_flexible = self.profile.get("compensation", {}).get("flexible", True)

        # Remote preference
        self.remote_only = self.profile.get("location", {}).get("remote_only", False)

    def match(self, job: JobData) -> MatchResult:
        """
        Match a job against the profile using description-centric scoring.

        The algorithm prioritizes job description analysis over title matching,
        recognizing that a "Staff PM" with AI/ML heavy description is more
        relevant than an "AI PM" with generic description.

        Args:
            job: Job data to match

        Returns:
            MatchResult with scoring details
        """
        description = job.description or ""
        title = job.title or ""

        # Check negative keywords against job title
        # Title-based check prevents rejecting good PM jobs whose descriptions
        # happen to mention negative terms (e.g., "reports to engineering manager")
        negative_matches = []
        for pattern, keyword in zip(self.negative_patterns, self.negative_keywords):
            if pattern.search(title):
                negative_matches.append(keyword)

        # If negative keywords found in title, reject (unless target company)
        if negative_matches:
            company_tier = self.company_tiers.get(job.company.lower())
            if not company_tier:
                return MatchResult(
                    matched=False,
                    score=0,
                    negative_matches=negative_matches,
                )

        # === DESCRIPTION ANALYSIS (Primary focus) ===
        desc_primary_matches = []  # Unique keywords found
        desc_keyword_count = 0  # Total mentions

        for pattern, keyword in zip(self.primary_patterns, self.primary_keywords):
            matches = pattern.findall(description)
            if matches:
                desc_primary_matches.append(keyword)
                desc_keyword_count += len(matches)

        desc_secondary_matches = []
        for pattern, keyword in zip(self.secondary_patterns, self.secondary_keywords):
            matches = pattern.findall(description)
            if matches:
                desc_secondary_matches.append(keyword)
                desc_keyword_count += len(matches)

        # === TITLE ANALYSIS ===
        # Check for exact title match
        title_exact_match = any(p.search(title) for p in self.title_patterns)

        # Calculate partial title match score
        title_partial_score = self._calculate_title_relevance(title)

        # Check if primary keywords appear in title (e.g., "AI" in title)
        title_has_primary = any(p.search(title) for p in self.primary_patterns)

        # === COMBINED KEYWORD MATCHES (for backward compatibility) ===
        matched_primary = list(set(desc_primary_matches))
        matched_secondary = list(set(desc_secondary_matches))

        # Also check title for keywords not in description
        for pattern, keyword in zip(self.primary_patterns, self.primary_keywords):
            if pattern.search(title) and keyword not in matched_primary:
                matched_primary.append(keyword)

        # === OTHER FACTORS ===
        company_tier = self.company_tiers.get(job.company.lower())

        salary_match = True
        if job.salary_min and job.salary_max:
            if job.salary_max < self.min_salary or job.salary_min > self.max_salary:
                if not self.salary_flexible:
                    salary_match = False

        remote_match = True
        if self.remote_only and not job.remote:
            remote_match = False

        # === MATCH DETERMINATION ===
        # Title-gating: require the title to be relevant (contains a core role
        # term like "product manager") unless the job is at a target company.
        # This prevents "Senior Software Engineer" roles with "AI" in the
        # description from appearing in results.
        has_relevant_title = title_exact_match or title_partial_score > 0.1

        matched = (
            (has_relevant_title and (len(desc_primary_matches) > 0 or title_has_primary)) or
            company_tier is not None
        )

        # === CALCULATE SCORE ===
        score = self._calculate_score_v2(
            desc_primary_matches=desc_primary_matches,
            desc_secondary_matches=desc_secondary_matches,
            desc_keyword_count=desc_keyword_count,
            title_exact_match=title_exact_match,
            title_partial_score=title_partial_score,
            title_has_primary=title_has_primary,
            company_tier=company_tier,
            salary_match=salary_match,
            remote_match=remote_match,
        )

        return MatchResult(
            matched=matched,
            score=score,
            matched_primary=matched_primary,
            matched_secondary=matched_secondary,
            matched_title=title_exact_match,
            matched_company_tier=company_tier,
            negative_matches=negative_matches,
            salary_match=salary_match,
            remote_match=remote_match,
            description_keyword_count=desc_keyword_count,
            description_keyword_variety=len(desc_primary_matches) + len(desc_secondary_matches),
            title_partial_match=title_partial_score,
        )

    # Seniority prefixes stripped when extracting core role terms.
    # These are universal across industries and not role-specific.
    _SENIORITY_PREFIXES = [
        "senior ", "sr. ", "sr ", "lead ", "staff ", "principal ",
        "director of ", "director, ", "group ", "head of ", "vp of ",
        "vp, ", "chief ", "associate ", "junior ",
    ]

    def _extract_core_role_terms(self) -> set[str]:
        """Extract core role terms from configured target titles.

        Strips seniority prefixes and comma suffixes to get the essential
        role name.  E.g.:
          "Senior AI Product Manager"  → "ai product manager"
          "Product Manager, AI"        → "product manager"
          "Lead Data Scientist"        → "data scientist"
          "Staff Backend Engineer"     → "backend engineer"
        """
        core_terms = set()
        for t in self.all_target_titles:
            t_lower = t.lower().strip()
            # Strip one seniority prefix from the beginning
            for prefix in self._SENIORITY_PREFIXES:
                if t_lower.startswith(prefix):
                    t_lower = t_lower[len(prefix):]
                    break
            # Handle comma suffixes: "Product Manager, AI" → "product manager"
            core = t_lower.split(",")[0].strip()
            if core:
                core_terms.add(core)
                # Add "management" variant for "manager" terms so
                # "Director of Product Management" matches alongside
                # "Director of Product Manager" style titles.
                if core.endswith(" manager"):
                    core_terms.add(core[:-len("manager")] + "management")
        return core_terms

    def _calculate_title_relevance(self, title: str) -> float:
        """Calculate partial title relevance score (0-1).

        Fully dynamic — derives relevance from the user's configured target
        titles rather than any hardcoded role or domain terms.

        Scoring approach:
          1. Exact regex match to a target title → 1.0
          2. Contains a core role term (e.g. "product manager") → 0.3 base
             + up to 0.7 from word overlap with the best-matching target title
          3. No core role match → 0.1 (very low)
        """
        title_lower = title.lower()

        # Exact match from target titles gets full score
        if any(p.search(title) for p in self.title_patterns):
            return 1.0

        # Title must contain at least one core role term
        has_core_role = any(term in title_lower for term in self.core_role_terms)
        if not has_core_role:
            return 0.1

        # Calculate best word overlap with any configured title
        title_words = set(title_lower.split())
        best_overlap = 0.0
        for configured_title in self.all_target_titles:
            configured_words = set(configured_title.lower().split())
            if not configured_words:
                continue
            common = title_words & configured_words
            overlap = len(common) / len(configured_words)
            best_overlap = max(best_overlap, overlap)

        # 0.3 base (has core role) + up to 0.7 scaled by word overlap
        return min(1.0, 0.3 + best_overlap * 0.7)

    def _calculate_score_v2(
        self,
        desc_primary_matches: list[str],
        desc_secondary_matches: list[str],
        desc_keyword_count: int,
        title_exact_match: bool,
        title_partial_score: float,
        title_has_primary: bool,
        company_tier: Optional[int],
        salary_match: bool,
        remote_match: bool,
    ) -> float:
        """
        Calculate match score using description-centric algorithm.

        New weights:
        - Description keyword relevance: 40% (primary focus)
        - Title relevance: 20% (reduced, partial credit)
        - Keyword variety & density: 15% (how many different keywords, frequency)
        - Company tier: 15%
        - Salary/Remote: 10%

        This ensures a "Staff PM" with heavy AI/ML description scores higher
        than an "AI PM" with generic description.
        """
        score = 0.0

        # === DESCRIPTION KEYWORD RELEVANCE (40%) ===
        # This is the primary signal - what's in the job description
        max_primary = len(self.primary_keywords)
        if max_primary > 0 and len(desc_primary_matches) > 0:
            # Variety: what percentage of primary keywords appear?
            variety_score = len(desc_primary_matches) / max_primary

            # Density bonus: more mentions = more relevant (capped)
            # 1-2 mentions = base, 3-5 = bonus, 6+ = max bonus
            density_multiplier = min(1.5, 1.0 + (desc_keyword_count - 1) * 0.1)

            desc_score = variety_score * density_multiplier * 100
            score += 0.40 * min(100, desc_score)

        # === TITLE RELEVANCE (20%) ===
        # Partial credit for related titles
        if title_exact_match:
            score += 0.20 * 100
        else:
            # Partial credit based on title analysis
            score += 0.20 * (title_partial_score * 100)

            # Bonus if primary keyword in title (e.g., "AI" in "AI Product Manager")
            if title_has_primary:
                score += 0.05 * 100  # 5% bonus

        # === KEYWORD VARIETY & DENSITY (15%) ===
        # Rewards jobs that mention multiple relevant areas
        total_variety = len(desc_primary_matches) + len(desc_secondary_matches)
        max_variety = len(self.primary_keywords) + len(self.secondary_keywords)

        if max_variety > 0:
            variety_pct = total_variety / max_variety
            # Secondary keywords in description show depth
            secondary_bonus = len(desc_secondary_matches) * 0.05
            variety_score = min(1.0, variety_pct + secondary_bonus) * 100
            score += 0.15 * variety_score

        # === COMPANY TIER (15%) ===
        if company_tier:
            tier_scores = {1: 100, 2: 70, 3: 40}
            score += 0.15 * tier_scores.get(company_tier, 0)

        # === SALARY & REMOTE (10%) ===
        if salary_match:
            score += 0.05 * 100
        if remote_match:
            score += 0.05 * 100

        return min(100, max(0, score))

    def get_search_queries(self) -> list[str]:
        """Get search queries from profile for collectors.

        Uses only the configured target titles (primary + secondary) as
        search queries. This produces more relevant results than appending
        keywords to role names, which job boards interpret as broad keyword
        searches and return unrelated roles.
        """
        seen = set()
        queries = []

        primary_titles = self.profile.get("target_titles", {}).get("primary", [])
        secondary_titles = self.profile.get("target_titles", {}).get("secondary", [])

        for title in primary_titles + secondary_titles:
            key = title.strip().lower()
            if key and key not in seen:
                seen.add(key)
                queries.append(title.strip())

        return queries
