import logging
import os
import pickle
from datetime import date

import pandas as pd
from pydantic import validate_call

from src.comments import get_all_canadian_observations_with_flagged_comments_df
from src.custom_logging import log_call
from src.dates import get_recent_dates
from src.emails import render_email_body, send_smtp_emails
from src.pydantic_models import EmailTable
from src.settings import AppEnvironment, Settings

log = logging.getLogger("comments_report")


@validate_call
def load_cached_data(s: Settings) -> pd.DataFrame | None:
    """Load cached comments data only in development"""
    if s.environment == AppEnvironment.DEVELOPMENT and os.path.exists(
        s.comments_cached_file
    ):
        log.info("Loading cached comments data")
        with open(s.comments_cached_file, "rb") as f:
            return pickle.load(f)
    return None


@validate_call(config={"arbitrary_types_allowed": True})
def save_cache(s: Settings, df: pd.DataFrame):
    """Save comments data to disk cache only in development"""
    if s.environment == AppEnvironment.DEVELOPMENT:
        log.info("Saving comments data to cache")
        os.makedirs(os.path.dirname(s.comments_cached_file), exist_ok=True)
        with open(s.comments_cached_file, "wb") as f:
            pickle.dump(df, f)


@log_call
@validate_call(config={"arbitrary_types_allowed": True})
def build_comments_email_tables(df: pd.DataFrame):
    """Create HTML tables from comments dataframe for email body"""
    log.info("Building email tables from comments data")
    if df.empty:
        return []
    return [
        EmailTable(
            title="Flagged Comments",
            html=df.to_html(render_links=True, justify="center"),
        )
    ]


@log_call
@validate_call(config={"arbitrary_types_allowed": True})
def send_flagged_comments_email(
    s: Settings,
    df_flagged_comments: pd.DataFrame,
    date_from: date,
    date_to: date,
):
    """Send email with flagged comments to recipients"""
    log.info(f"Preparing flagged comments email for period {date_from} to {date_to}")
    # Generate email subject using template
    error = df_flagged_comments.empty
    subject = s.comments_email_subject_template.render(
        date_from=date_from, date_to=date_to, error=error
    )
    # Build HTML tables and email body
    tables = build_comments_email_tables(df_flagged_comments)
    body = render_email_body(
        s.comments_email_body_template,
        tables,
        s.comments_email_error_message if error else s.comments_email_empty_message,
    )
    # Send email to all recipients
    send_smtp_emails(s, s.comments_email_recipients, subject, body)
    log.info("All flagged comments emails sent successfully.")


async def generate_and_send_comments_report(s: Settings):
    """Main function to generate and email flagged comments report"""
    log.info("Starting comments report generation")

    # Get date range for report
    dates = get_recent_dates(s.number_days_back)
    log.info(f"Processing comments for period: {dates[0]} to {dates[-1]}")

    try:
        # Try loading cached data
        comments_df = load_cached_data(s)

        # If no cache or empty DataFrame, fetch new data
        if comments_df is None or comments_df.empty:
            log.info("Fetching new comments data")
            comments_df = await get_all_canadian_observations_with_flagged_comments_df(
                s, dates, [s.iconic_taxa]
            )
            log.info(f"Retrieved {len(comments_df)} flagged comments")
            save_cache(s, comments_df)
    except Exception:
        # Log any errors and create empty dataframe
        log.exception("Error generating comments report")
        comments_df = pd.DataFrame()

    # Send email with results
    log.info("Sending comments report email")
    send_flagged_comments_email(s, comments_df, dates[0], dates[-1])


if __name__ == "__main__":
    # run with "python -m src.comments_report"
    import asyncio

    from dotenv import load_dotenv

    # Load environment variables and configure logging
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("geopy").setLevel(logging.WARNING)

    # Initialize settings and run main function
    s = Settings()
    asyncio.run(generate_and_send_comments_report(s))
