# Import libraries
import numpy as np
import pandas as pd

# Global function - Haversine distance formula for aalclating the distance between two points with respect to
# curvature of earths radius
EARTH_RADIUS = 6371


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    r = EARTH_RADIUS  # Radius of earth in kilometers
    return c * r


def euclidean_distance(x1, y1, x2, y2):
    """
    Cartesian distance between two sets of points in a projected CRS (e.g. EPSG:3006).
    All coordinates are expected in meters.
    Supports scalars, 1D arrays, or pandas Series.
    """

    dx = x2 - x1
    dy = y2 - y1
    return np.sqrt(dx**2 + dy**2)  # Standard euclidean distance formula


def evaluate_coordinates(y_true_lat, y_true_lon, y_pred_lat, y_pred_lon, zones_true=None, zones_pred=None) -> dict:
    """
    Evaluate models for spatial coordinates prediction using Haversine distance.
    Returns a dictionary of metrics ready to be logged to MLflow.
    """
    distances = haversine_distance(y_true_lat, y_true_lon, y_pred_lat, y_pred_lon)

    metrics = {"median_error_km": np.median(distances), "mean_error_km": np.mean(distances), "max_error_km": np.max(distances)}

    # Calculate in-radius metrics
    thresholds = [0.5, 1, 3, 5, 10]
    for r in thresholds:
        percent = np.mean(distances <= r) * 100
        metrics[f"in_radius_{r}km_pct"] = percent

    # If zones are predicted, calculate E[D] (Expected Coordinate Error) handling correct/wrong zones
    if zones_pred is not None and zones_true is not None:
        df = pd.DataFrame({"true_zone": zones_true, "pred_zone": zones_pred, "error_km": distances})

        df["zone_correct"] = df["true_zone"] == df["pred_zone"]

        # Expected error calculations
        group_stats = df.groupby("zone_correct")["error_km"].agg(["count", "mean"])
        group_stats["proportion"] = group_stats["count"] / len(df)
        group_stats["weighted_error"] = group_stats["mean"] * group_stats["proportion"]

        expected_error = group_stats["weighted_error"].sum()
        metrics["expected_distance_error_km"] = expected_error

        # Mean error breakdown by Zone specifically
        zone_perf = df.groupby("true_zone")["error_km"].mean().to_dict()
        for zone_name, err in zone_perf.items():
            # Clean string for mlflow metric naming
            clean_name = str(zone_name).replace(" ", "_").replace("-", "")
            metrics[f"zone_{clean_name}_mean_err_km"] = err

    return metrics


def evaluate_projected_coordinates(x_true, y_true, x_pred, y_pred, zones_true=None, zones_pred=None) -> dict:
    """
    Evaluate spatial coordinate predictions in a projected CRS (e.g. EPSG:3006).
    Distances are computed as Euclidean distances in meters.

    x_*, y_* are coordinates in meters (after CRS transform).
    """
    # 1. Distances in meters
    distances_m = euclidean_distance(x_true, y_true, x_pred, y_pred)
    # Convert the distance into km
    distances = distances_m / 1000.0

    # 2. Basic error metrics (meters and km)
    metrics = {
        # "median_error_m": float(np.median(distances_m)),
        # "mean_error_m": float(np.mean(distances_m)),
        # "max_error_m": float(np.max(distances_m)),
        "median_error_km": float(np.median(distances_m) / 1000.0),
        "mean_error_km": float(np.mean(distances_m) / 1000.0),
        "max_error_km": float(np.max(distances_m) / 1000.0),
    }

    # 3. In-radius metrics (default thresholds in km)
    # Calculate in-radius metrics
    # Set the threshold in radius of km
    thresholds = [0.5, 1, 3, 5, 10]
    for r in thresholds:
        percent = np.mean(distances <= r) * 100
        metrics[f"in_radius_{r}km_pct"] = percent

    # 4. Zone-based expected error (same logic as your haversine version)
    if zones_pred is not None and zones_true is not None:
        df = pd.DataFrame(
            {
                "true_zone": zones_true,
                "pred_zone": zones_pred,
                "error_m": distances_m,
            }
        )

        df["zone_correct"] = df["true_zone"] == df["pred_zone"]

        group_stats = df.groupby("zone_correct")["error_m"].agg(["count", "mean"])
        group_stats["proportion"] = group_stats["count"] / len(df)
        group_stats["weighted_error"] = group_stats["mean"] * group_stats["proportion"]

        expected_error_m = group_stats["weighted_error"].sum()
        metrics["expected_distance_error_m"] = float(expected_error_m)
        metrics["expected_distance_error_km"] = float(expected_error_m / 1000.0)

        # Mean error per true zone
        zone_perf = df.groupby("true_zone")["error_m"].mean().to_dict()
        for zone_name, err_m in zone_perf.items():
            clean_name = str(zone_name).replace(" ", "_").replace("-", "")
            metrics[f"zone_{clean_name}_mean_err_m"] = float(err_m)
            metrics[f"zone_{clean_name}_mean_err_km"] = float(err_m / 1000.0)

    return metrics
