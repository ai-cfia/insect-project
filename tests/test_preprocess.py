import copy
import unittest
from unittest.mock import patch

import pandas as pd

from src.observation_reports import exclude_non_invasive
from src.preprocess import (
    add_location_details,
    add_location_details_df,
    clean_and_format_df,
    filter_ca_us_locations,
    flag_comments,
    group_by_taxa,
    keep_only_first_sample_image,
)
from src.pydantic_models import ObservationSummary
from tests import settings


class TestFilterNorthAmericanLocations(unittest.TestCase):
    def setUp(self):
        self.settings = settings.model_copy()
        self.settings.coords_column = "coordinates"
        self.settings.city_column = "City"
        self.settings.province_column = "Province"

    @patch("src.preprocess.get_city_province_country")
    def test_filter_north_american_locations(self, mock_get_city_province_country):
        mock_get_city_province_country.side_effect = [
            ("Ottawa", "ON", "ca"),
            ("New York", "NY", "us"),
            ("Paris", "Île-de-France", "fr"),
        ]

        test_data = {
            "coordinates": [
                (45.4215, -75.6993),
                (40.7128, -74.0060),
                (48.8566, 2.3522),
            ],
            "City": ["Ottawa", "New York", "Paris"],
            "Province": ["ON", "NY", "Île-de-France"],
            "Country": ["ca", "us", "fr"],
        }

        df = pd.DataFrame(test_data)
        filtered_df = filter_ca_us_locations(self.settings, df)

        expected_data = {
            "City": ["Ottawa", "New York"],
            "Province": ["ON", "NY"],
        }
        expected_df = pd.DataFrame(expected_data)

        pd.testing.assert_frame_equal(filtered_df, expected_df)

    @patch("src.preprocess.get_city_province_country")
    def test_filter_all_non_north_american_locations(
        self, mock_get_city_province_country
    ):
        mock_get_city_province_country.side_effect = [
            ("Paris", "Île-de-France", "fr"),
            ("Tokyo", "Tokyo", "jp"),
        ]

        test_data = {
            "coordinates": [
                (48.8566, 2.3522),
                (35.6895, 139.6917),
            ],
            "Country": ["fr", "jp"],
        }

        df = pd.DataFrame(test_data)
        filtered_df = filter_ca_us_locations(self.settings, df)

        self.assertTrue(filtered_df.empty)

    @patch("src.preprocess.get_city_province_country")
    def test_filter_empty_dataframe(self, mock_get_city_province_country):
        df = pd.DataFrame({"coordinates": [], "Country": []})
        filtered_df = filter_ca_us_locations(self.settings, df)
        self.assertTrue(filtered_df.empty)

    def test_filter_missing_country_column(self):
        test_data = {
            "coordinates": [
                (45.4215, -75.6993),
                (40.7128, -74.0060),
            ]
        }
        df = pd.DataFrame(test_data)
        filtered_df = filter_ca_us_locations(self.settings, df)
        pd.testing.assert_frame_equal(filtered_df, df)


class TestExtractFirstSampleImage(unittest.TestCase):
    def setUp(self):
        self.settings = settings.model_copy()
        self.settings.image_column = "Sample_Img"
        self.test_data = pd.DataFrame(
            {
                "Sample_Img": [
                    ["image1.jpg", "image2.jpg"],
                    ["image3.jpg"],
                    [],
                    None,
                    ["image4.jpg", "image5.jpg"],
                ]
            }
        )

    def test_extract_first_sample_image(self):
        expected_output = pd.DataFrame(
            {
                "Sample_Img": [
                    "image1.jpg",
                    "image3.jpg",
                    None,
                    None,
                    "image4.jpg",
                ]
            }
        )

        result = keep_only_first_sample_image(self.settings, self.test_data.copy())

        pd.testing.assert_frame_equal(result, expected_output)

    def test_missing_sample_img_column(self):
        df = pd.DataFrame({"Other_Column": [1, 2, 3]})
        self.settings.image_column = "Sample_Img"
        result = keep_only_first_sample_image(self.settings, df.copy())
        pd.testing.assert_frame_equal(result, df)


class TestSplitByTaxonomy(unittest.TestCase):
    def setUp(self):
        self.settings = settings.model_copy()
        self.settings.upper_taxa_column = "upper taxa"
        self.settings.upper_taxa = ["Insecta", "Mollusca", "Plantae", "Fungi"]

        self.test_data = {
            "Species": [
                "Species1",
                "Species2",
                "Species3",
                "Species4",
                "Species5",
                "Species6",
            ],
            "upper taxa": [
                "Insecta",
                "Mollusca",
                "Plantae",
                "Fungi",
                "Unknown",
                "Insecta",
            ],
            "Value": [10, 20, 30, 40, 50, 60],
        }
        self.df = pd.DataFrame(self.test_data)

    def test_correct_number_of_outputs(self):
        results = group_by_taxa(self.settings, self.df)
        self.assertEqual(len(results), len(self.settings.upper_taxa) + 1)

    def test_individual_taxa_dataframes(self):
        insecta_df, mollusca_df, plantae_df, fungi_df, others_df = group_by_taxa(
            self.settings, self.df
        )

        for taxon, df_out in zip(
            self.settings.upper_taxa, [insecta_df, mollusca_df, plantae_df, fungi_df]
        ):
            expected = (
                self.df[self.df[self.settings.upper_taxa_column] == taxon]
                .drop(columns=[self.settings.upper_taxa_column])
                .reset_index(drop=True)
            )
            pd.testing.assert_frame_equal(df_out, expected)

    def test_others_dataframe(self):
        *_, others_df = group_by_taxa(self.settings, self.df)

        expected_others = (
            self.df[
                ~self.df[self.settings.upper_taxa_column].isin(self.settings.upper_taxa)
            ]
            .drop(columns=[self.settings.upper_taxa_column])
            .reset_index(drop=True)
        )

        if expected_others.empty:
            self.assertIsNone(others_df)
        else:
            pd.testing.assert_frame_equal(others_df, expected_others)

    def test_empty_dataframe(self):
        empty_df = pd.DataFrame(columns=["Species", "upper taxa", "Value"])
        results = group_by_taxa(self.settings, empty_df)
        for df in results:
            self.assertTrue(df is None or df.empty)

    def test_missing_taxa_column(self):
        df_no_taxa = self.df.drop(columns=["upper taxa"])
        with self.assertRaises(KeyError):
            group_by_taxa(self.settings, df_no_taxa)


class TestExcludeNonInvasive(unittest.TestCase):
    def setUp(self):
        self.s = copy.deepcopy(settings.model_copy())
        self.s.name_alt_column = "Scientific Name"
        self.df = pd.DataFrame(
            {
                "Scientific Name": [
                    "Species A",
                    "Monochamus scutellatus",
                    "Species C",
                    "Species D",
                ]
            }
        )

    def test_exclude_matching_species(self):
        result = exclude_non_invasive(self.s, self.df)
        self.assertEqual(len(result), 3)
        self.assertNotIn(
            "Monochamus scutellatus", result[self.s.name_alt_column].values
        )

    def test_exclude_no_match(self):
        self.s.species_data.non_invasive = [self.s.species_data.invasive[0]]
        result = exclude_non_invasive(self.s, self.df)
        self.assertEqual(len(result), 4)

    def test_exclude_empty_list(self):
        self.s.species_data.non_invasive = []
        result = exclude_non_invasive(self.s, self.df)
        self.assertEqual(len(result), 4)


class TestAddLocationDetailsDF(unittest.TestCase):
    def setUp(self):
        self.settings = settings.model_copy()
        self.settings.coords_column = "coordinates"
        self.settings.city_column = "City"
        self.settings.province_column = "Province"

    @patch("src.preprocess.get_city_province_country")
    def test_add_location_details_df(self, mock_get_city_province_country):
        mock_get_city_province_country.side_effect = [
            ("Ottawa", "ON", "ca"),
            ("New York", "NY", "us"),
            ("Paris", "Île-de-France", "fr"),
        ]

        test_data = {
            "coordinates": [
                (45.4215, -75.6993),
                (40.7128, -74.0060),
                (48.8566, 2.3522),
            ]
        }

        df = pd.DataFrame(test_data)
        result_df = add_location_details_df(self.settings, df)

        expected_data = {
            "coordinates": [
                (45.4215, -75.6993),
                (40.7128, -74.0060),
                (48.8566, 2.3522),
            ],
            "City": ["Ottawa", "New York", "Paris"],
            "Province": ["ON", "NY", "Île-de-France"],
            "Country": ["ca", "us", "fr"],
        }
        expected_df = pd.DataFrame(expected_data)

        pd.testing.assert_frame_equal(result_df, expected_df)

    def test_add_location_details_df_empty(self):
        df = pd.DataFrame({"coordinates": []})
        result_df = add_location_details_df(self.settings, df)
        self.assertTrue(result_df.empty)


class TestFlagComments(unittest.TestCase):
    def setUp(self):
        self.settings = settings.model_copy()
        self.settings.comment_flags = ["invasive", "pest", "harmful"]

    def test_flag_comments_with_matches(self):
        summary = ObservationSummary(
            id=1,
            comments=[
                "This species is invasive",
                "Looks like a harmful pest",
                "Normal observation",
            ],
        )
        result = flag_comments(self.settings, summary)
        self.assertEqual(
            result.flagged_comments,
            ["this species is invasive", "looks like a harmful pest"],
        )
        self.assertEqual(result.flagged_terms, [["invasive"], ["harmful", "pest"]])
        self.assertEqual(len(result.flagged_comments), 2)
        self.assertEqual(len(result.flagged_terms), 2)

    def test_flag_comments_no_matches(self):
        summary = ObservationSummary(
            id=1, comments=["Normal observation", "Another normal comment"]
        )
        result = flag_comments(self.settings, summary)
        self.assertEqual(result.flagged_comments, [])
        self.assertEqual(result.flagged_terms, [])

    def test_flag_comments_empty(self):
        summary = ObservationSummary(id=1, comments=[])
        result = flag_comments(self.settings, summary)
        self.assertEqual(result.flagged_comments, [])
        self.assertEqual(result.flagged_terms, [])


class TestCleanAndFormatDF(unittest.TestCase):
    def setUp(self):
        self.s = settings.model_copy()
        self.s.coords_column = "Coordinates"
        self.s.city_column = "City"
        self.s.province_column = "Province"
        self.s.image_column = "Image URLs"
        self.s.observation_id_column = "Observation ID"

        self.columns = [
            self.s.observation_id_column,
            self.s.city_column,
            self.s.province_column,
            self.s.image_column,
        ]

    @patch("src.preprocess.get_city_province_country")
    def test_clean_and_format_df_happy_path(self, mock_get_location):
        mock_get_location.side_effect = [
            ("Ottawa", "ON", "ca"),
            ("New York", "NY", "us"),
        ]

        df = pd.DataFrame(
            {
                "Observation ID": [1, 2],
                "Coordinates": [(45.4215, -75.6993), (40.7128, -74.0060)],
                "Image URLs": [["img1.jpg", "img2.jpg"], ["img3.jpg"]],
            }
        )

        result = clean_and_format_df(self.s, df, self.columns)

        expected = pd.DataFrame(
            {
                "Observation ID": [2, 1],
                "City": ["New York", "Ottawa"],
                "Province": ["NY", "ON"],
                "Image URLs": ["img3.jpg", "img1.jpg"],
            }
        ).reset_index(drop=True)

        pd.testing.assert_frame_equal(result, expected)

    @patch("src.preprocess.get_city_province_country")
    def test_clean_and_format_df_with_duplicates(self, mock_get_location):
        mock_get_location.side_effect = [
            ("Ottawa", "ON", "ca"),
        ]

        df = pd.DataFrame(
            {
                "Observation ID": [1, 1],
                "Coordinates": [(45.4215, -75.6993), (45.4215, -75.6993)],
                "Image URLs": [["img1.jpg"], ["img1.jpg"]],
            }
        )

        result = clean_and_format_df(self.s, df, self.columns)

        expected = pd.DataFrame(
            {
                "Observation ID": [1],
                "City": ["Ottawa"],
                "Province": ["ON"],
                "Image URLs": ["img1.jpg"],
            }
        ).reset_index(drop=True)

        pd.testing.assert_frame_equal(result, expected)

    @patch("src.preprocess.get_city_province_country")
    def test_clean_and_format_df_empty_input(self, mock_get_location):
        df = pd.DataFrame(columns=["Observation ID", "Coordinates", "Image URLs"])
        result = clean_and_format_df(self.s, df, self.columns)
        self.assertTrue(result.empty)

    @patch("src.preprocess.get_city_province_country")
    def test_clean_and_format_df_non_north_american(self, mock_get_location):
        mock_get_location.side_effect = [
            ("Paris", "Île-de-France", "fr"),
            ("Tokyo", "Tokyo", "jp"),
        ]

        df = pd.DataFrame(
            {
                "Observation ID": [1, 2],
                "Coordinates": [(48.8566, 2.3522), (35.6895, 139.6917)],
                "Image URLs": [["img1.jpg"], ["img2.jpg"]],
            }
        )

        result = clean_and_format_df(self.s, df, self.columns)
        self.assertTrue(result.empty)


class TestAddLocationDetails(unittest.TestCase):
    def setUp(self):
        """Set up common test variables"""
        self.settings = settings
        self.settings.api_request_delay = 0.0
        self.summary_with_coords = ObservationSummary(
            id=1,
            coordinates=[-79.3832, 43.6532],
        )
        self.summary_without_coords = ObservationSummary(id=2, coordinates=[])

    @patch("src.preprocess.get_city_province_country")
    def test_add_location_details_with_coordinates(
        self, mock_get_city_province_country
    ):
        """Test that location details are added when coordinates exist"""
        mock_get_city_province_country.return_value = ("Toronto", "Ontario", "Canada")

        result = add_location_details(self.settings, self.summary_with_coords)

        self.assertEqual(result.city, "Toronto")
        self.assertEqual(result.province, "Ontario")
        self.assertEqual(result.country, "Canada")
        mock_get_city_province_country.assert_called_once_with(
            self.settings, 43.6532, -79.3832
        )

    def test_add_location_details_without_coordinates(self):
        """Test that location details remain None when no coordinates exist"""
        result = add_location_details(self.settings, self.summary_without_coords)

        self.assertIsNone(result.city)
        self.assertIsNone(result.province)
        self.assertIsNone(result.country)
