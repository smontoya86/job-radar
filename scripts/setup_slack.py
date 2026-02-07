#!/usr/bin/env python3
"""Setup script for Slack webhook notifications."""
import asyncio
import logging
import sys

from scripts.bootstrap import settings
from src.logging_config import setup_logging
from src.notifications.slack_notifier import SlackNotifier

logger = logging.getLogger(__name__)


async def test_webhook(webhook_url: str) -> bool:
    """Test the webhook by sending a test message."""
    notifier = SlackNotifier(webhook_url=webhook_url)
    return await notifier.send_test_message()


def main():
    """Run Slack setup."""
    setup_logging()

    print("Slack Webhook Setup")
    print("=" * 50)
    print()

    # Check for existing webhook
    if settings.slack_webhook_url:
        logger.info("Found existing webhook URL in settings.")
        print()

        # Test it
        logger.info("Testing webhook...")
        success = asyncio.run(test_webhook(settings.slack_webhook_url))

        if success:
            logger.info("Webhook is working! Check your Slack channel for a test message.")
            return 0
        else:
            logger.error("Webhook test failed. Please check the URL.")
            print()

    print("To set up Slack notifications:")
    print()
    print("1. Go to https://api.slack.com/apps")
    print("2. Click 'Create New App' > 'From scratch'")
    print("3. Name it 'Job Radar' and select your workspace")
    print("4. Go to 'Incoming Webhooks' in the sidebar")
    print("5. Toggle 'Activate Incoming Webhooks' to ON")
    print("6. Click 'Add New Webhook to Workspace'")
    print("7. Select the channel for notifications")
    print("8. Copy the webhook URL")
    print()

    webhook_url = input("Enter your Slack webhook URL (or press Enter to skip): ").strip()

    if not webhook_url:
        print("Skipped. You can add the webhook URL to your .env file later:")
        print("SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...")
        return 0

    # Test the webhook
    print()
    logger.info("Testing webhook...")
    success = asyncio.run(test_webhook(webhook_url))

    if success:
        logger.info("Success! Check your Slack channel for a test message.")
        print()
        print("Add this to your .env file:")
        print("SLACK_WEBHOOK_URL=%s" % webhook_url)
        return 0
    else:
        logger.error("Test failed. Please check the URL and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
