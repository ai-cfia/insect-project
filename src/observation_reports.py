import logging
import os
from datetime import date, datetime

import pandas as pd
from pydantic import validate_call
from tqdm import tqdm

from src.custom_logging import log_call
from src.dates import get_yesterday
from src.emails import render_email_body, send_smtp_emails
from src.models import PredictionLabel, load_densenet_model, predict_invasiveness
from src.observations import get_observation_summaries_df
from src.preprocess import clean_and_format_df, exclude_non_invasive, group_by_taxa
from src.pydantic_models import EmailTable
from src.settings import Settings
from src.species import get_specie_ids

log = logging.getLogger("observation_reports")


@log_call
@validate_call(config=dict(arbitrary_types_allowed=True))
def build_observations_email_tables(s: Settings, df: pd.DataFrame, df_us: pd.DataFrame):
    log.info("Building email tables from observation data")
    # Get list of taxa categories including "Other"
    categories = s.upper_taxa + [s.other_taxa_label]

    # Group observations by taxa for both CA and US
    all_dfs = [
        ("iconic_taxa", group_by_taxa(s, df)),
        ("US iconic_taxa", group_by_taxa(s, df_us)),
    ]

    # Create HTML tables for each non-empty taxa group
    tables = [
        EmailTable(
            title=f"{prefix}: {name}",
            html=df.to_html(render_links=True, justify="center"),
        )
        for prefix, dfs in all_dfs
        for df, name in zip(dfs, categories)
        if df is not None and not df.empty
    ]
    return tables


@log_call
@validate_call(config=dict(arbitrary_types_allowed=True))
def send_observation_report_email(
    s: Settings,
    ca_summaries_df: pd.DataFrame,
    us_summaries_df: pd.DataFrame,
    observations_date: date,
    error: bool = False,
):
    """Send email with observation reports to recipients"""
    log.info(f"Preparing observation report email for {observations_date}")
    # Generate email subject using template
    subject = s.observations_email_subject_template.render(
        date_on=observations_date, error=error
    )
    # Build HTML tables and email body
    tables = build_observations_email_tables(s, ca_summaries_df, us_summaries_df)
    body = render_email_body(
        s.observations_email_body_template,
        tables,
        s.observations_email_empty_message,
    )
    # Send email to all recipients
    send_smtp_emails(s, s.observations_email_recipients, subject, body)
    log.info("All observations emails sent successfully.")


@log_call
@validate_call
async def generate_and_send_observation_report(
    s: Settings, observations_date: date | None = None
):
    """Generate and send observation report email with ML predictions."""
    log.info("Starting observation report generation")
    # Get list of regulated species IDs and report date
    regulated_taxon_ids = await get_specie_ids(s)

    if observations_date is None:
        report_date_env = os.getenv("REPORT_DATE", "").strip()
        if report_date_env:
            try:
                observations_date = datetime.strptime(report_date_env, "%Y-%m-%d").date()
            except ValueError as e:
                raise ValueError(
                    "Invalid REPORT_DATE format. Expected YYYY-MM-DD."
                ) from e
        else:
            observations_date = get_yesterday()

    log.info(f"Processing observations for date: {observations_date}")

    # Load pre-trained DenseNet model
    log.info("Loading DenseNet model")
    model = load_densenet_model(s.species_classification_model_path)

    # Process Canadian observations
    log.info("Fetching Canadian observations")
    ca_summaries_df = await get_observation_summaries_df(
        s=s,
        taxon_ids=regulated_taxon_ids,
        date_on=observations_date,
        area=s.areas.CA,
    )
    log.info(f"Retrieved {len(ca_summaries_df)} Canadian observations")

    # Initialize ML predictions and filter initial dataset
    ca_summaries_df[s.ml_column] = ""
    ca_summaries_df = exclude_non_invasive(s, ca_summaries_df)
    log.info(
        f"Filtered to {len(ca_summaries_df)} Canadian observations after excluding non-invasive species"
    )

    # Process non-invasive species
    # Get observations for each non-invasive species, predict their class,
    # and keep only those incorrectly predicted as invasive
    log.info("Processing non-invasive species observations")
    for non_invasive_specie in tqdm(
        s.species_data.non_invasive, desc="Processing non-invasive species"
    ):
        if not non_invasive_specie.id:
            continue
        df = await get_observation_summaries_df(
            s,
            taxon_ids=[non_invasive_specie.id],
            date_on=observations_date,
            area=s.areas.CA,
        )
        df[s.ml_column] = predict_invasiveness(
            s, df[s.image_column], model, PredictionLabel.NON_INVASIVE
        )
        df = df[df[s.ml_column] == PredictionLabel.INVASIVE.value].reset_index(
            drop=True
        )
        ca_summaries_df = pd.concat([ca_summaries_df, df], ignore_index=True)

    # Process invasive species
    # For each invasive species in the dataset, predict whether their
    # images match expected invasive characteristics
    log.info("Processing invasive species observations")
    for invasive_specie in tqdm(
        s.species_data.invasive, desc="Processing invasive species"
    ):
        if not invasive_specie.name:
            continue
        images = ca_summaries_df[
            ca_summaries_df[s.name_alt_column] == invasive_specie.name
        ][s.image_column]
        ca_summaries_df.loc[
            ca_summaries_df[s.name_alt_column] == invasive_specie.name, s.ml_column
        ] = predict_invasiveness(s, images, model, PredictionLabel.INVASIVE)

    # Clean and format final Canadian dataset
    log.info("Cleaning and formatting Canadian observations")
    ca_summaries_df = clean_and_format_df(s, ca_summaries_df, s.observation_columns_ca)

    # Process US observations
    log.info("Processing US observations")
    us_summaries_df = await get_observation_summaries_df(
        s=s,
        taxon_ids=s.us_regulated_taxon_ids,
        date_on=observations_date,
        area=s.areas.US,
    )
    log.info(f"Retrieved {len(us_summaries_df)} US observations")
    us_summaries_df = clean_and_format_df(s, us_summaries_df, s.observation_columns_us)

    # Generate and send email report
    log.info("Sending observation report email")
    send_observation_report_email(
        s,
        ca_summaries_df,
        us_summaries_df,
        observations_date,
        error=not regulated_taxon_ids,
    )


if __name__ == "__main__":
    # run with `python -m src.observation_reports`
    import asyncio
    import logging

    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("geopy").setLevel(logging.WARNING)

    settings = Settings()
    asyncio.run(generate_and_send_observation_report(settings))
