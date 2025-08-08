import logging
import re

import pandas as pd
from pydantic import validate_call

from src.custom_logging import log_call
from src.geo import get_city_province_country
from src.pydantic_models import ObservationSummary
from src.settings import Settings

log = logging.getLogger(__name__)


@log_call
@validate_call(config=dict(arbitrary_types_allowed=True))
def add_location_details_df(s: Settings, df: pd.DataFrame):
    """Add city, province and country columns based on coordinates"""
    df[s.city_column] = ""
    df[s.province_column] = ""

    if df.empty:
        log.debug("Input DataFrame is empty.")
        return df

    locations = [
        get_city_province_country(s, lat, lon) for lon, lat in df[s.coords_column]
    ]
    if not locations:
        return df[[s.coords_column]].drop(columns=[s.coords_column])

    cities, provinces, countries = zip(*locations) if locations else ([], [], [])

    df[s.city_column] = cities
    df[s.province_column] = provinces
    df["Country"] = [c.lower() for c in countries]

    return df


@log_call
@validate_call
def add_location_details(s: Settings, summary: ObservationSummary):
    """Add city, province and country based on coordinates to an ObservationSummary"""
    if summary.coordinates:
        summary.city, summary.province, summary.country = get_city_province_country(
            s, summary.coordinates[1], summary.coordinates[0]
        )
    return summary


@log_call
@validate_call(config=dict(arbitrary_types_allowed=True))
def filter_ca_us_locations(s: Settings, df: pd.DataFrame):
    """Keep only Canadian and US locations"""
    country_column = "Country"

    if country_column not in df.columns:
        log.debug(f"Column '{country_column}' missing. Skipping filtering.")
        return df

    df = df.loc[df[country_column].isin({"ca", "us"})].copy()
    df.drop(columns=[s.coords_column, country_column], inplace=True, errors="ignore")
    df.reset_index(drop=True, inplace=True)

    return df


@log_call
@validate_call(config=dict(arbitrary_types_allowed=True))
def keep_only_first_sample_image(s: Settings, df: pd.DataFrame):
    """Keep only first image from list of sample images"""
    if s.image_column not in df.columns:
        log.debug(f"Column '{s.image_column}' not found.")
        return df

    df[s.image_column] = df[s.image_column].apply(
        lambda images: images[0] if images and len(images) > 0 else None
    )

    return df


@log_call
@validate_call(config=dict(arbitrary_types_allowed=True))
def group_by_taxa(s: Settings, df_regulated: pd.DataFrame):
    """Split DataFrame into groups by taxonomic category"""
    taxa_dfs = {
        taxon: df_regulated[df_regulated[s.upper_taxa_column] == taxon]
        .drop(columns=[s.upper_taxa_column])
        .reset_index(drop=True)
        for taxon in s.upper_taxa
    }

    df_others = df_regulated[~df_regulated[s.upper_taxa_column].isin(s.upper_taxa)]
    df_others = (
        df_others.drop(columns=[s.upper_taxa_column]).reset_index(drop=True)
        if not df_others.empty
        else None
    )

    return (*taxa_dfs.values(), df_others)


@log_call
@validate_call(config=dict(arbitrary_types_allowed=True))
def exclude_non_invasive(s: Settings, df: pd.DataFrame):
    """Remove non-invasive species from DataFrame"""
    excluded_species = [s.name for s in s.species_data.non_invasive if s.name]
    if not excluded_species:
        return df
    pattern = "|".join(excluded_species)
    return df[~df[s.name_alt_column].str.contains(pattern, na=False)].reset_index(
        drop=True
    )


@log_call
@validate_call(config=dict(arbitrary_types_allowed=True))
def clean_and_format_df(s: Settings, df: pd.DataFrame, columns: list[str]):
    """Clean and format DataFrame by removing duplicates, adding locations, filtering and sorting"""
    df = df.drop_duplicates(subset=[s.observation_id_column]).reset_index(drop=True)
    df = add_location_details_df(s, df)
    df = filter_ca_us_locations(s, df)
    df = df[columns]
    df = df.sort_values(by=[s.province_column]).reset_index(drop=True)
    return keep_only_first_sample_image(s, df)


@log_call
@validate_call
def flag_comments(s: Settings, summary: ObservationSummary):
    """Flag comments containing specified terms in an observation summary"""
    if not summary.cleaned_comments or not s.comment_flags:
        summary.flagged_comments = []
        summary.flagged_terms = []
        return summary

    pattern = re.compile(
        r"\b(" + "|".join(map(re.escape, s.comment_flags)) + r")\b", re.IGNORECASE
    )

    flagged_comments: list[str] = []
    flagged_terms: list[list[str]] = []

    for comment in summary.cleaned_comments:
        matches = pattern.findall(comment)
        if matches:
            seen = set()
            terms = [t for t in matches if not (t in seen or seen.add(t))]
            flagged_comments.append(comment)
            flagged_terms.append(terms)

    summary.flagged_comments = flagged_comments
    summary.flagged_terms = flagged_terms
    return summary


if __name__ == "__main__":
    # Run with `python -m src.preprocess`
    from dotenv import load_dotenv

    load_dotenv()
    s = Settings()
    test_data = {
        s.coords_column: [
            (45.4215, -75.6993),  # Ottawa, CA
            (40.7128, -74.0060),  # New York, US
            (48.8566, 2.3522),  # Paris, FR (should be filtered out)
        ],
        s.image_column: [
            ["image1.jpg", "image2.jpg"],  # List of images
            ["image3.jpg"],  # Single image in list
            [],  # Empty list
        ],
    }

    df = pd.DataFrame(test_data)

    # Test filter_north_american_locations
    filtered_df = filter_ca_us_locations(s, df)
    print("Filtered DataFrame:")
    print(filtered_df)

    # Test extract_first_sample_image
    updated_df = keep_only_first_sample_image(s, filtered_df)
    print("\nUpdated DataFrame with Sample_Img processing:")
    print(updated_df)

    # Test data for split_by_taxonomy
    test_taxa_data = {
        "Species": ["Species1", "Species2", "Species3", "Species4", "Species5"],
        "upper taxa": ["Insecta", "Mollusca", "Plantae", "Fungi", "Unknown"],
        "Value": [10, 20, 30, 40, 50],
    }

    df_taxa = pd.DataFrame(test_taxa_data)
    upper_taxa_list = ["Insecta", "Mollusca", "Plantae", "Fungi"]

    # Test split_by_taxonomy
    insecta_df, mollusca_df, plantae_df, fungi_df, others_df = group_by_taxa(
        s, df_taxa, upper_taxa_list
    )

    print("\nInsecta DataFrame:")
    print(insecta_df)

    print("\nMollusca DataFrame:")
    print(mollusca_df)

    print("\nPlantae DataFrame:")
    print(plantae_df)

    print("\nFungi DataFrame:")
    print(fungi_df)

    print("\nOthers DataFrame:")
    print(others_df)
