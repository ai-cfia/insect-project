import argparse
import asyncio
import logging
import os
from enum import Enum

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.comments_report import generate_and_send_comments_report
from src.observation_reports import generate_and_send_observation_report
from src.settings import Settings


class ReportType(str, Enum):
    """Enum for supported report types"""

    COMMENTS = "comments"
    OBSERVATIONS = "observations"


class ReportConfig(BaseModel):
    """Configuration for report generation"""

    report_type: ReportType = Field(
        description="Type of report to generate", examples=["comments", "observations"]
    )


def setup_logging():
    """Configure logging settings"""
    smtp_debug_level = os.getenv("SMTP_DEBUG_LEVEL", "0")
    app_log_level = logging.DEBUG if smtp_debug_level not in {"", "0"} else logging.INFO

    logging.basicConfig(level=app_log_level)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("geopy").setLevel(logging.WARNING)


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Run different types of reports")
    parser.add_argument(
        "report_type",
        choices=[rt.value for rt in ReportType],
        help="Type of report to generate",
    )
    args = parser.parse_args()

    # Validate arguments using Pydantic
    try:
        config = ReportConfig(report_type=args.report_type)
    except ValueError as e:
        print(f"Error: {e}")
        return

    # Load environment variables and setup logging
    load_dotenv()
    setup_logging()

    # Initialize settings
    settings = Settings()

    # Run the selected report using match statement
    match config.report_type:
        case ReportType.COMMENTS:
            asyncio.run(generate_and_send_comments_report(settings))
        case ReportType.OBSERVATIONS:
            asyncio.run(generate_and_send_observation_report(settings))


if __name__ == "__main__":
    main()
