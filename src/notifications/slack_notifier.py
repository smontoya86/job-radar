"""Slack notifications for job alerts."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

import aiohttp

from src.matching.scorer import ScoredJob

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Send job alerts to Slack via webhook."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        min_score: float = 60,
        remote_only: bool = False,  # Changed default to False to notify for all jobs
    ):
        """
        Initialize Slack notifier.

        Args:
            webhook_url: Slack incoming webhook URL
            min_score: Minimum score to send notification
            remote_only: Only notify for remote jobs
        """
        self.webhook_url = webhook_url
        self.min_score = min_score
        self.remote_only = remote_only

    async def notify(self, job: ScoredJob) -> bool:
        """
        Send a single job notification.

        Args:
            job: Scored job to notify about

        Returns:
            True if notification sent successfully
        """
        if not self.webhook_url:
            logger.info("Slack webhook not configured")
            return False

        if job.score < self.min_score:
            return False

        if self.remote_only and not job.job.remote:
            return False

        payload = self._build_payload(job)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200

        except Exception as e:
            logger.error("Slack notification error: %s", e)
            return False

    async def notify_batch(self, jobs: list[ScoredJob]) -> int:
        """
        Send notifications for multiple jobs.

        Args:
            jobs: List of scored jobs

        Returns:
            Number of successful notifications
        """
        if not self.webhook_url:
            return 0

        # Filter by minimum score and remote preference
        eligible = [j for j in jobs if j.score >= self.min_score]

        if self.remote_only:
            eligible = [j for j in eligible if j.job.remote]

        if not eligible:
            return 0

        # Send summary if many jobs
        if len(eligible) > 5:
            await self._send_summary(eligible)
            return len(eligible)

        # Send individual notifications
        success_count = 0
        for job in eligible:
            if await self.notify(job):
                success_count += 1
            # Rate limit
            await asyncio.sleep(0.5)

        return success_count

    async def _send_summary(self, jobs: list[ScoredJob]) -> bool:
        """Send a summary notification for many jobs."""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🎯 {len(jobs)} New Job Matches Found!",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Found {len(jobs)} jobs matching your criteria*",
                },
            },
            {"type": "divider"},
        ]

        # Add top 10 jobs
        for job in jobs[:10]:
            j = job.job
            score_emoji = "🔥" if job.score >= 80 else "✨" if job.score >= 60 else "📋"

            # Build keywords string
            keywords = ", ".join(job.matched_keywords[:5])

            # Build salary string
            salary_str = ""
            if j.salary_min and j.salary_max:
                salary_str = f" | ${j.salary_min//1000}k-${j.salary_max//1000}k"
            elif j.salary_min:
                salary_str = f" | ${j.salary_min//1000}k+"

            # Remote indicator
            remote_str = " 🏠" if j.remote else ""

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{score_emoji} *<{j.url}|{j.title}>*\n"
                            f"_{j.company}_{remote_str}{salary_str}\n"
                            f"Score: {job.score:.0f} | {keywords}"
                        ),
                    },
                }
            )

        if len(jobs) > 10:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"_...and {len(jobs) - 10} more jobs_",
                        }
                    ],
                }
            )

        payload = {"blocks": blocks}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error("Slack summary error: %s", e)
            return False

    def _build_payload(self, job: ScoredJob) -> dict:
        """Build Slack message payload for a single job."""
        j = job.job

        # Score emoji
        if job.score >= 80:
            score_emoji = "🔥"
            score_text = "Excellent Match"
        elif job.score >= 60:
            score_emoji = "✨"
            score_text = "Good Match"
        else:
            score_emoji = "📋"
            score_text = "Potential Match"

        # Build salary string
        salary_str = "Not specified"
        if j.salary_min and j.salary_max:
            salary_str = f"${j.salary_min:,} - ${j.salary_max:,}"
        elif j.salary_min:
            salary_str = f"${j.salary_min:,}+"
        elif j.salary_max:
            salary_str = f"Up to ${j.salary_max:,}"

        # Location with remote indicator
        location_str = j.location or "Not specified"
        if j.remote:
            location_str += " 🏠"

        # Keywords
        keywords = ", ".join(job.matched_keywords[:8])

        # Company tier indicator
        tier_str = ""
        if job.match_result.matched_company_tier:
            tier_map = {1: "⭐⭐⭐", 2: "⭐⭐", 3: "⭐"}
            tier_str = f" {tier_map.get(job.match_result.matched_company_tier, '')}"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{score_emoji} {score_text}: {job.score:.0f}/100",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*<{j.url}|{j.title}>*\n*{j.company}*{tier_str}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Location:*\n{location_str}"},
                    {"type": "mrkdwn", "text": f"*Salary:*\n{salary_str}"},
                    {"type": "mrkdwn", "text": f"*Source:*\n{j.source}"},
                    {"type": "mrkdwn", "text": f"*Keywords:*\n{keywords}"},
                ],
            },
        ]

        # Add apply button if URL available
        if j.apply_url or j.url:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Apply Now",
                                "emoji": True,
                            },
                            "url": j.apply_url or j.url,
                            "style": "primary",
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "View Job",
                                "emoji": True,
                            },
                            "url": j.url,
                        },
                    ],
                }
            )

        # Add timestamp
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Found at {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    }
                ],
            }
        )

        return {"blocks": blocks}

    async def send_test_message(self) -> bool:
        """Send a test message to verify webhook is working."""
        if not self.webhook_url:
            return False

        payload = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "✅ *Job Radar Connected!*\nSlack notifications are working.",
                    },
                }
            ]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200
        except Exception:
            return False
