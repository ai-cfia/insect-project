import logging
from datetime import date

from pydantic import validate_call
from tqdm import tqdm
from tqdm.asyncio import tqdm as tqdm_async

from src.custom_logging import log_call
from src.observations import get_all_observations, transform_summaries_to_df
from src.preprocess import (
    add_location_details,
    flag_comments,
    keep_only_first_sample_image,
)
from src.pydantic_models import ObservationSummary
from src.settings import Settings

log = logging.getLogger(__name__)


@log_call
@validate_call
async def get_canadian_observations_with_flagged_comments(
    s: Settings, date_on: date, iconic_taxa: list[str]
):
    """Get Canadian observations with flagged comments for given date and taxa."""
    # Get all observations for the given date and taxa
    observations = await get_all_observations(
        s=s, iconic_taxa=iconic_taxa, date_on=date_on, area=s.areas.CA
    )
    # Filter to only observations with comments
    observations = [
        o
        for o in tqdm(observations, desc="Filtering observations with comments")
        if o.comments_count > 0
    ]
    # Convert to summaries and add location details
    summaries = [
        add_location_details(s, ObservationSummary.model_validate(o.model_dump()))
        for o in tqdm(observations, desc="Generating observation summary locations")
    ]
    # Filter to only Canadian observations
    summaries = [
        summary
        for summary in tqdm(summaries, desc="Filtering for Canada")
        if summary.country == "ca"
    ]
    # Flag comments containing terms of interest
    summaries = [
        flag_comments(s, summary)
        for summary in tqdm(summaries, desc="Flagging comments")
    ]
    # Keep only summaries with flagged comments
    summaries = [s for s in summaries if s.flagged_comments]
    return summaries


@log_call
@validate_call
async def get_all_canadian_observations_with_flagged_comments_df(
    s: Settings, dates: list[date], iconic_taxa: list[str]
):
    """Get DataFrame of Canadian observations with flagged comments for date range."""
    if not dates:
        raise ValueError("No dates provided.")
    # Get summaries for all dates
    all_summaries = []
    for d in tqdm_async(dates, desc="Processing dates"):
        all_summaries.extend(
            await get_canadian_observations_with_flagged_comments(s, d, iconic_taxa)
        )
    # Convert summaries to DataFrame and process
    summaries_df = transform_summaries_to_df(all_summaries, s.df_column_map_default)
    summaries_df = keep_only_first_sample_image(s, summaries_df)
    # Explode flagged comments and terms into separate rows
    summaries_df = summaries_df.explode(
        [s.flagged_comments_column, s.flagged_terms_column], ignore_index=True
    )
    # Filter and select columns
    summaries_df = summaries_df[summaries_df[s.flagged_comments_column].notna()]
    summaries_df = summaries_df[s.comments_columns]
    return summaries_df


if __name__ == "__main__":
    # run with python -m src.comments
    import asyncio
    import logging
    from datetime import date

    from dotenv import load_dotenv

    from src.dates import get_recent_dates

    # from src.dates import get_yesterday

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    async def main():
        # Initialize settings and parameters
        s = Settings()
        iconic_taxa = ["insecta"]

        dates = get_recent_dates(1)

        # Get flagged comments DataFrame
        df = await get_all_canadian_observations_with_flagged_comments_df(
            s, dates, iconic_taxa
        )

        print(f"Flagged observations in Canada from {dates[0]} to {dates[-1]}.\n", df)

    asyncio.run(main())
