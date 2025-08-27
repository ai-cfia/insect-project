from enum import Enum

from inaturalist_client import Configuration
from jinja2 import Environment, FileSystemLoader, Template
from pydantic import EmailStr, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings

from src.pydantic_models import Area, AreaData, ObservationSummary, Species, SpeciesData

# TODO: Add validation for configuration values


class AppEnvironment(str, Enum):
    """Environment settings for app"""

    PRODUCTION = "prod"
    DEVELOPMENT = "dev"


class Settings(BaseSettings):
    """Main settings class containing all configuration"""

    # Environment settings
    environment: AppEnvironment = AppEnvironment.PRODUCTION
    number_days_back: int = 7
    nominatim_user_agent: str = "inectsiNatApp"

    # API settings
    inat_host: str = "https://api.inaturalist.org/v1"
    api_request_delay: float = 3.0

    # Project and taxonomy settings
    project_id: str = "91863"
    us_regulated_taxon_ids: list[str] = ["324726", "325295", "471260", "497733"]
    iconic_taxa: str = "insecta"
    upper_taxa: list[str] = ["Insecta", "Plantae", "Mollusca", "Fungi", "Chromista"]
    other_taxa_label: str = (
        "Others (recently added species which do not belong to the above) .."
    )

    # Species configuration
    species_data: SpeciesData = SpeciesData(
        invasive=[
            Species(name="Asian Long-horned Beetle"),
            Species(name="Citrus Longhorn Beetle"),
        ],
        non_invasive=[Species(name="Monochamus scutellatus", id="82043")],
    )
    species_classification_model_path: str = "models/densenet_model_beta_AsianLonghorn"

    # Geographic settings
    areas: AreaData = AreaData(
        CA=Area(nelat=83.1, nelng=-50.75, swlat=41.2833333, swlng=-140.8833333),
        US=Area(nelat=49.386847, nelng=-50.954936, swlat=25.489156, swlng=-128.826023),
    )

    # DataFrame column names
    ml_column: str = "ai_visionVerification"
    name_column: str = "Common Name"
    name_alt_column: str = "Scientific Name"
    image_column: str = "Image URLs"
    observation_id_column: str = "Observation ID"
    observation_url_column: str = "Observation URL"
    coords_column: str = "Coordinates"
    posted_on_column: str = "Posted On"
    observed_on_column: str = "Observed On"
    user_login_column: str = "User"
    upper_taxa_column: str = "Taxon Group"
    upper_taxa_id_column: str = "Taxon ID"
    city_column: str = "City"
    province_column: str = "Province"
    country_column: str = "Country"
    quality_column: str = "Quality Grade"
    flagged_comments_column: str = "Flagged Comments"
    flagged_terms_column: str = "Flagged Terms"

    # Comment settings
    comment_flags: list[str] = [
        "new specie",
        "first record",
        "first detection",
        "first canadian",
        "first north american",
        "new",
        "brand new",
        "unknown",
        "cfia",
        "canadian food inspection agency",
    ]
    comments_cached_file: str = "cache/cached_comments.pkl"

    # Email settings
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: SecretStr
    smtp_debug_level: int = 0
    sender_email: EmailStr
    sender_name: str = "AI LAB CFIA"
    email_template_dir: str = "templates"
    subscription_manager_url: str | None = None
    contact_email: EmailStr | None = None
    ai_lab_url: str = "https://github.com/ai-cfia/"
    observations_email_recipients: list[EmailStr] | None = []
    observations_email_subject_template_name: str = "observations_email_subject.j2"
    observations_email_body_template_name: str = "email_body.html"
    observations_email_empty_message: str = "No observations found"
    observations_email_error_message: str = (
        "An error occurred while processing observations"
    )
    comments_email_recipients: list[EmailStr] | None = []
    comments_email_subject_template_name: str = "comments_email_subject.j2"
    comments_email_body_template_name: str = "email_body.html"
    comments_email_empty_message: str = "No flagged comments found"
    comments_email_error_message: str = "An error occurred while processing comments"

    # Image processing settings
    image_resize: int = 255
    image_crop_size: int = 224
    image_normalize_mean_rgb: tuple[float, float, float] = (0.485, 0.456, 0.406)
    image_normalize_std_rgb: tuple[float, float, float] = (0.229, 0.224, 0.225)

    @computed_field
    @property
    def df_column_map_default(self) -> dict[str, str]:
        """Default mapping of model fields to DataFrame columns"""
        return {
            "id": self.observation_id_column,
            "quality_grade": self.quality_column,
            "name": self.name_column,
            "name_alt": self.name_alt_column,
            "uri": self.observation_url_column,
            "image_urls": self.image_column,
            "coordinates": self.coords_column,
            "created_at": self.posted_on_column,
            "observed_at": self.observed_on_column,
            "username": self.user_login_column,
            "taxon_name": self.upper_taxa_column,
            "taxon_id": self.upper_taxa_id_column,
            "flagged_comments": self.flagged_comments_column,
            "flagged_terms": self.flagged_terms_column,
            "city": self.city_column,
            "province": self.province_column,
            "country": self.country_column,
        }

    @computed_field
    @property
    def observation_columns_us(self) -> list[str]:
        """Columns for US observations"""
        return [
            self.quality_column,
            self.name_column,
            self.name_alt_column,
            self.city_column,
            self.province_column,
            self.observation_url_column,
            self.image_column,
            self.posted_on_column,
            self.observed_on_column,
            self.user_login_column,
            self.upper_taxa_column,
            self.observation_id_column,
        ]

    @computed_field
    @property
    def observation_columns_ca(self) -> list[str]:
        """Columns for Canadian observations (includes ML column)"""
        return self.observation_columns_us + [self.ml_column]

    @computed_field
    @property
    def comments_columns(self) -> list[str]:
        """Columns for comment analysis"""
        return [
            self.flagged_comments_column,
            self.name_column,
            self.name_alt_column,
            self.city_column,
            self.province_column,
            self.observation_url_column,
            self.image_column,
            self.posted_on_column,
            self.flagged_terms_column,
        ]

    @computed_field
    @property
    def inat_client_config(self) -> Configuration:
        """iNaturalist API client configuration"""
        return Configuration(host=self.inat_host, retries=5)

    @computed_field
    @property
    def template_loader(self) -> FileSystemLoader:
        """Jinja template loader"""
        return FileSystemLoader(self.email_template_dir)

    @computed_field
    @property
    def template_env(self) -> Environment:
        """Jinja environment configuration"""
        env = Environment(loader=self.template_loader, autoescape=True)
        env.globals["subscription_manager_url"] = self.subscription_manager_url
        env.globals["contact_email"] = self.contact_email
        env.globals["ai_lab_url"] = self.ai_lab_url
        return env

    @computed_field
    @property
    def observations_email_subject_template(self) -> Template:
        """Template for observation email subjects"""
        return self.template_env.get_template(
            self.observations_email_subject_template_name
        )

    @computed_field
    @property
    def observations_email_body_template(self) -> Template:
        """Template for observation email bodies"""
        return self.template_env.get_template(
            self.observations_email_body_template_name
        )

    @computed_field
    @property
    def comments_email_subject_template(self) -> Template:
        """Template for comment email subjects"""
        return self.template_env.get_template(self.comments_email_subject_template_name)

    @computed_field
    @property
    def comments_email_body_template(self) -> Template:
        """Template for comment email bodies"""
        return self.template_env.get_template(self.comments_email_body_template_name)

    @model_validator(mode="after")
    def validate_computed_fields(self) -> "Settings":
        """Validate all computed fields and column mappings"""
        for name in self.model_computed_fields:
            _ = getattr(self, name)

        valid_keys = ObservationSummary.model_fields.keys()
        invalid = set(self.df_column_map_default.keys()) - set(valid_keys)
        if invalid:
            raise ValueError(f"Invalid df_column_map_default keys: {invalid}")

        return self
