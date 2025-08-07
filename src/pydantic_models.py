import re
from datetime import datetime

from pydantic import (
    AliasChoices,
    AliasPath,
    BaseModel,
    Field,
    computed_field,
    field_validator,
)


class Species(BaseModel):
    """Model for species data with optional name and ID"""

    name: str | None = None
    id: str | None = None


class SpeciesData(BaseModel):
    """Container for invasive and non-invasive species lists"""

    invasive: list[Species] | None = []
    non_invasive: list[Species] | None = []


class Area(BaseModel):
    """Geographic bounding box defined by NE and SW coordinates"""

    nelat: float | None = None
    nelng: float | None = None
    swlat: float | None = None
    swlng: float | None = None


class AreaData(BaseModel):
    """Container for CA and US area definitions"""

    CA: Area | None = None
    US: Area | None = None


class ObservationSummary(BaseModel):
    """Summary of an iNaturalist observation with location and taxonomic details"""

    id: int
    quality_grade: str | None = None
    name: str | None = Field(
        "",
        validation_alias=AliasChoices(
            "name", AliasPath("taxon", "preferred_common_name")
        ),
    )
    name_alt: str | None = Field(
        "", validation_alias=AliasChoices("name_alt", AliasPath("taxon", "name"))
    )
    uri: str | None = ""
    image_urls: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("image_urls", AliasPath("photos")),
    )
    coordinates: list[float] | None = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "coordinates", AliasPath("geojson", "coordinates")
        ),
    )
    created_at: datetime | None = Field(
        None,
        validation_alias=AliasChoices(
            "created_at", AliasPath("created_at_details", "var_date")
        ),
    )
    observed_at: datetime | None = Field(
        None, validation_alias=AliasChoices("observed_at", AliasPath("observed_on"))
    )
    username: str | None = Field(
        "", validation_alias=AliasChoices("username", AliasPath("user", "login"))
    )
    taxon_name: str | None = Field(
        "",
        validation_alias=AliasChoices(
            "taxon_name", AliasPath("taxon", "iconic_taxon_name")
        ),
    )
    taxon_id: int | None = Field(
        None, validation_alias=AliasChoices("taxon_id", AliasPath("taxon", "id"))
    )
    comments: list[str] | None = None
    flagged_comments: list[str] | None = None
    flagged_terms: list[list[str]] | None = None
    city: str | None = None
    province: str | None = None
    country: str | None = None

    @field_validator("image_urls", mode="before")
    @classmethod
    def extract_image_urls(cls, value: list[str]):
        """Convert photo URLs to large format"""
        if isinstance(value, list):
            return [
                v["url"].replace("square", "large")
                if isinstance(v, dict) and "url" in v
                else v.replace("square", "large")
                if isinstance(v, str)
                else v
                for v in value
            ]
        return []

    @field_validator("comments", mode="before")
    @classmethod
    def extract_comments(cls, value):
        """Extract comment bodies from comment objects"""
        if isinstance(value, list):
            return [v["body"] if isinstance(v, dict) else v for v in value]

    @computed_field
    @property
    def cleaned_comments(self) -> list[str] | None:
        """Clean comments by removing emojis and special characters"""
        if not self.comments:
            return None
        return [
            re.sub(
                r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]+",
                "",
                re.sub(r"[^\w\s]", "", comment.lower()),
            ).strip()
            for comment in self.comments
        ]


class EmailTable(BaseModel):
    """Email table with title and HTML content"""

    title: str
    html: str
