import logging
import time

from geopy.geocoders import Nominatim
from pydantic import validate_call

from src.custom_logging import log_call
from src.settings import Settings

log = logging.getLogger(__name__)


@log_call
@validate_call
def get_city_province_country(s: Settings, lat: float, lon: float):
    locator = Nominatim(user_agent=s.nominatim_user_agent, timeout=10)
    try:
        log.debug("Nominatim request throttling: sleeping 1.2s")
        time.sleep(1.2)
        location = locator.reverse((lat, lon), language="en")
        address = location.raw["address"] if location and location.raw else {}
        city = (
            address.get("city", "")
            or address.get("town", "")
            or address.get("village", "")
            or address.get("municipality", "")
            or address.get("county", "")
            or address.get("state_district", "")
        )
        province, country = address.get("state", ""), address.get("country_code", "")
        return city, province, country
    except Exception as e:
        log.info(f"Reverse geocoding failed for ({lat}, {lon}): {e}")
        log.debug(f"Reverse geocoding failed for ({lat}, {lon}): {e}")
        return "", "", ""


if __name__ == "__main__":
    # Test coordinates (latitude, longitude)
    # Run: python -m src.geo
    from dotenv import load_dotenv

    load_dotenv()

    s = Settings()
    test_coords = [
        [40.7128, -74.0060],
        (51.5074, -0.1278),
        (35.6895, 139.6917),
        (-33.8688, 151.2093),
        (48.8566, 2.3522),
    ]

    for coord in test_coords:
        city, province, country = get_city_province_country(s, coord[0], coord[1])
        print(
            f"Coordinates: {coord} -> City: {city}, Province: {province}, Country: {country}"
        )
