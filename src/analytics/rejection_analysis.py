"""Rejection analysis to identify resume gaps."""
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.persistence.models import Application, Job


@dataclass
class KeywordGap:
    """A keyword found in job descriptions but not in profile."""
    keyword: str
    frequency: int  # How many rejected jobs mentioned it
    example_companies: list[str]  # Companies that required it


@dataclass
class RejectionInsight:
    """Insights from analyzing rejected applications."""
    total_rejected: int
    analyzed_with_descriptions: int
    top_missing_keywords: list[KeywordGap]
    top_required_skills: list[tuple[str, int]]  # (skill, count)
    common_requirements: list[str]
    recommendations: list[str]


class RejectionAnalyzer:
    """Analyze rejected applications to identify resume gaps."""

    # Common skills/requirements to look for in job descriptions
    SKILL_PATTERNS = [
        # Technical skills
        r'\b(python|sql|java|javascript|typescript|go|rust|scala)\b',
        r'\b(aws|gcp|azure|cloud)\b',
        r'\b(kubernetes|docker|k8s)\b',
        r'\b(machine learning|ml|deep learning|neural network)\b',
        r'\b(llm|large language model|gpt|generative ai|genai)\b',
        r'\b(nlp|natural language processing)\b',
        r'\b(data science|data analytics|analytics)\b',
        r'\b(a/?b testing|experimentation)\b',
        r'\b(agile|scrum|kanban)\b',
        r'\b(sql|nosql|postgresql|mysql|mongodb|redis)\b',
        r'\b(api|rest|graphql)\b',
        r'\b(ci/?cd|devops)\b',
        # Product skills
        r'\b(product strategy|roadmap|roadmapping)\b',
        r'\b(user research|customer research|discovery)\b',
        r'\b(prds?|product requirements?)\b',
        r'\b(okrs?|kpis?|metrics)\b',
        r'\b(stakeholder management)\b',
        r'\b(cross[- ]functional)\b',
        r'\b(go[- ]to[- ]market|gtm)\b',
        r'\b(product[- ]led growth|plg)\b',
        # Domain expertise
        r'\b(b2b|enterprise|saas)\b',
        r'\b(b2c|consumer)\b',
        r'\b(e[- ]?commerce|marketplace)\b',
        r'\b(fintech|payments|banking)\b',
        r'\b(healthcare|health[- ]?tech)\b',
        r'\b(adtech|advertising)\b',
        r'\b(search|discovery|personalization|recommendations?)\b',
        r'\b(mobile|ios|android)\b',
        r'\b(platform|infrastructure)\b',
        # Experience requirements
        r'\b(\d+\+?\s*years?)\b',
        r'\b(senior|staff|principal|director|lead)\b',
        r'\b(mba|technical degree|cs degree)\b',
    ]

    # Keywords that indicate specific requirements
    REQUIREMENT_INDICATORS = [
        r'required:?\s*(.+?)(?:\n|$)',
        r'must have:?\s*(.+?)(?:\n|$)',
        r'requirements?:?\s*(.+?)(?:\n|$)',
        r'qualifications?:?\s*(.+?)(?:\n|$)',
        r'you have:?\s*(.+?)(?:\n|$)',
        r'experience with:?\s*(.+?)(?:\n|$)',
    ]

    def __init__(self, session: Session, profile_path: Optional[Path] = None):
        """Initialize analyzer with database session and profile."""
        self.session = session
        self.profile_path = profile_path or Path(__file__).parent.parent.parent / "config" / "profile.yaml"
        self.profile = self._load_profile()

    def _load_profile(self) -> dict:
        """Load the user's profile keywords."""
        if self.profile_path.exists():
            with open(self.profile_path) as f:
                return yaml.safe_load(f)
        return {}

    def _get_profile_keywords(self) -> set[str]:
        """Get all keywords from the user's profile."""
        keywords = set()

        # Add required keywords
        required = self.profile.get("required_keywords", {})
        for kw in required.get("primary", []):
            keywords.add(kw.lower())
        for kw in required.get("secondary", []):
            keywords.add(kw.lower())

        # Add target titles
        titles = self.profile.get("target_titles", {})
        for title in titles.get("primary", []):
            keywords.add(title.lower())
        for title in titles.get("secondary", []):
            keywords.add(title.lower())

        return keywords

    def _extract_skills(self, text: str) -> list[str]:
        """Extract skills and requirements from job description text."""
        text = text.lower()
        skills = []

        for pattern in self.SKILL_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            skills.extend(matches)

        return skills

    def _extract_requirements(self, text: str) -> list[str]:
        """Extract explicit requirements from job description."""
        requirements = []
        text_lower = text.lower()

        for pattern in self.REQUIREMENT_INDICATORS:
            matches = re.findall(pattern, text_lower)
            requirements.extend(matches)

        return requirements

    def get_rejected_applications_with_descriptions(self) -> list[tuple[Application, str]]:
        """Get rejected applications that have job descriptions."""
        results = []

        # Get rejected applications
        stmt = select(Application).where(Application.status == "rejected")
        apps = self.session.execute(stmt).scalars().all()

        for app in apps:
            description = None

            # Try to get description from linked job
            if app.job_id:
                job = self.session.get(Job, app.job_id)
                if job and job.description:
                    description = job.description

            # Try application's own job_description field
            if not description and app.job_description:
                description = app.job_description

            if description:
                results.append((app, description))

        return results

    def analyze(self) -> RejectionInsight:
        """Analyze rejected applications and identify gaps."""
        # Get rejected applications
        stmt = select(Application).where(Application.status == "rejected")
        all_rejected = self.session.execute(stmt).scalars().all()
        total_rejected = len(all_rejected)

        # Get ones with descriptions
        apps_with_desc = self.get_rejected_applications_with_descriptions()
        analyzed_count = len(apps_with_desc)

        if analyzed_count == 0:
            return RejectionInsight(
                total_rejected=total_rejected,
                analyzed_with_descriptions=0,
                top_missing_keywords=[],
                top_required_skills=[],
                common_requirements=[],
                recommendations=["Add job descriptions to rejected applications for analysis."],
            )

        # Extract skills from all job descriptions
        all_skills = []
        skill_by_company = {}

        for app, description in apps_with_desc:
            skills = self._extract_skills(description)
            all_skills.extend(skills)

            for skill in set(skills):
                if skill not in skill_by_company:
                    skill_by_company[skill] = []
                skill_by_company[skill].append(app.company)

        # Count skill frequency
        skill_counts = Counter(all_skills)
        top_skills = skill_counts.most_common(20)

        # Find missing keywords (in job descriptions but not in profile)
        profile_keywords = self._get_profile_keywords()
        missing_keywords = []

        for skill, count in top_skills:
            skill_lower = skill.lower()
            # Check if this skill is NOT in the profile
            is_in_profile = any(
                skill_lower in kw or kw in skill_lower
                for kw in profile_keywords
            )

            if not is_in_profile and count >= 2:  # Appears in at least 2 job descriptions
                missing_keywords.append(KeywordGap(
                    keyword=skill,
                    frequency=count,
                    example_companies=skill_by_company.get(skill, [])[:3],
                ))

        # Extract common explicit requirements
        all_requirements = []
        for app, description in apps_with_desc:
            reqs = self._extract_requirements(description)
            all_requirements.extend(reqs)

        req_counts = Counter(all_requirements)
        common_reqs = [req for req, count in req_counts.most_common(5) if count >= 2]

        # Generate recommendations
        recommendations = self._generate_recommendations(missing_keywords, top_skills)

        return RejectionInsight(
            total_rejected=total_rejected,
            analyzed_with_descriptions=analyzed_count,
            top_missing_keywords=missing_keywords[:10],
            top_required_skills=top_skills[:10],
            common_requirements=common_reqs,
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self,
        missing_keywords: list[KeywordGap],
        top_skills: list[tuple[str, int]],
    ) -> list[str]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []

        if missing_keywords:
            top_missing = [kw.keyword for kw in missing_keywords[:3]]
            recommendations.append(
                f"Consider adding these frequently requested skills to your resume: {', '.join(top_missing)}"
            )

        # Check for specific patterns
        skill_set = {s[0].lower() for s in top_skills}

        if any(s in skill_set for s in ['b2b', 'enterprise', 'saas']):
            recommendations.append(
                "Many roles require B2B/Enterprise/SaaS experience. Highlight relevant B2B product work."
            )

        if any(s in skill_set for s in ['sql', 'python', 'data']):
            recommendations.append(
                "Technical/data skills appear frequently. Emphasize hands-on technical experience."
            )

        if any(s in skill_set for s in ['5+', '7+', '10+']):
            recommendations.append(
                "Some roles require specific years of experience. Ensure your resume clearly states your experience level."
            )

        if not recommendations:
            recommendations.append(
                "Add job descriptions to more rejected applications for better analysis."
            )

        return recommendations

    def get_keyword_comparison(self, application_id: str) -> Optional[dict]:
        """Compare a specific application's job description to profile."""
        app = self.session.get(Application, application_id)
        if not app:
            return None

        description = None
        if app.job_id:
            job = self.session.get(Job, app.job_id)
            if job:
                description = job.description
        if not description:
            description = app.job_description

        if not description:
            return None

        job_skills = set(self._extract_skills(description))
        profile_keywords = self._get_profile_keywords()

        matched = job_skills & profile_keywords
        missing = job_skills - profile_keywords

        return {
            "company": app.company,
            "position": app.position,
            "matched_keywords": list(matched),
            "missing_keywords": list(missing),
            "match_percentage": len(matched) / len(job_skills) * 100 if job_skills else 0,
        }
