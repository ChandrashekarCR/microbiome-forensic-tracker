import numpy as np
import pandas as pd

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
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a)) 
    r = 6371 # Radius of earth in kilometers
    return c * r

def evaluate_coordinates(y_true_lat, y_true_lon, y_pred_lat, y_pred_lon, zones_true=None, zones_pred=None):
    """
    Evaluate models for spatial coordinates prediction using Haversine distance.
    Returns a dictionary of metrics ready to be logged to MLflow.
    """
    distances = haversine_distance(
        y_true_lat, y_true_lon, 
        y_pred_lat, y_pred_lon
    )
    
    metrics = {
        "median_error_km": np.median(distances),
        "mean_error_km": np.mean(distances),
        "max_error_km": np.max(distances)
    }
    
    # Calculate in-radius metrics
    thresholds = [0.5, 1, 3, 5,10]
    for r in thresholds:
        percent = np.mean(distances <= r) * 100
        metrics[f"in_radius_{r}km_pct"] = percent

    # If zones are predicted, calculate E[D] (Expected Coordinate Error) handling correct/wrong zones
    if zones_pred is not None and zones_true is not None:
        df = pd.DataFrame({
            'true_zone': zones_true,
            'pred_zone': zones_pred,
            'error_km': distances
        })
        
        df['zone_correct'] = df['true_zone'] == df['pred_zone']
        
        # Expected error calculations
        group_stats = df.groupby('zone_correct')['error_km'].agg(['count', 'mean'])
        group_stats['proportion'] = group_stats['count'] / len(df)
        group_stats['weighted_error'] = group_stats['mean'] * group_stats['proportion']
        
        expected_error = group_stats['weighted_error'].sum()
        metrics["expected_distance_error_km"] = expected_error
        
        # Mean error breakdown by Zone specifically
        zone_perf = df.groupby('true_zone')['error_km'].mean().to_dict()
        for zone_name, err in zone_perf.items():
            # Clean string for mlflow metric naming
            clean_name = str(zone_name).replace(" ", "_").replace("-", "")
            metrics[f"zone_{clean_name}_mean_err_km"] = err
            
    return metrics
