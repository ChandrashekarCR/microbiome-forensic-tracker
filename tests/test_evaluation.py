import numpy as np
import pytest

from src.ml.evaluation import haversine_distance,EARTH_RADIUS

# Test cases for latitude and longitude
PARIS = (48.8566, 2.3522)      
LONDON = (51.5074, -0.1278)
NORTH_POLE = (90.0, 0.0)
SOUTH_POLE = (-90.0, 0.0)
EQUATOR_POINT = (0.0, 0.0)

EXPECTED_PARIS_LONDON_KM = 343.0  # approximate, to be used with tolerance

@pytest.mark.parametrize(
    "lat1, lon1, lat2, lon2, expected_km",
    [
        (0.0, 0.0, 0.0, 0.0, 0.0),                     # same point
        (0.0, 0.0, 0.0, 1.0, 111.0),                   # 1 degree of longitude at equator
        (0.0, 0.0, 1.0, 0.0, 111.0),                   # 1 degree of latitude
        (*PARIS, *LONDON, EXPECTED_PARIS_LONDON_KM),   # city pair
    ],
)
def test_haversine_parametrized(lat1, lon1, lat2, lon2, expected_km):
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    assert dist == pytest.approx(expected_km, rel=0.02)