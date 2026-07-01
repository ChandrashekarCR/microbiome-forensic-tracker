import joblib
import pandas as pd
from pyproj import Transformer

from ml.config import config
from ml.evaluation import evaluate_projected_coordinates
from ml.models import TrainTestSplit, load_and_prep_data


def predict_and_evaluate_test_set():
    """
    Load the final fitted pipeline, predict on the blind 20% test set,
    and report honest final metrics.
    """
    # 1. Load the saved pipeline
    pipeline = joblib.load("/home/chandru/binp51/src/ml/mlruns/1/models/m-150112cb0dfd4175b98a23716a7f042b/artifacts/model.pkl")

    # 2. Reconstruct the exact same train/test split
    # Deterministic because random_state is fixed in config
    config.database.table = "malmo_species"
    df = load_and_prep_data()
    splitter = TrainTestSplit(
        df,
        n_splits=config.data_splitting.n_splits,
        test_size=config.data_splitting.test_size,
    )

    # 3. Get the blind test set — never seen during training or CV
    X_test, y_test_zone, y_test_coords = splitter.get_test_data()

    # 4. Predict — pipeline handles zeros_filter + k_best + RF internally
    preds = pipeline.predict(X_test)  # shape (n_test_samples, 2) → [X_meters, Y_meters]

    # 5. Evaluate with your existing evaluation function
    metrics = evaluate_projected_coordinates(
        x_true=y_test_coords["X_meters"].values,
        y_true=y_test_coords["Y_meters"].values,
        x_pred=preds[:, 0],
        y_pred=preds[:, 1],
        zones_true=y_test_zone.values,
    )

    print("Final Test Set Evaluation (blind 20%)\n")
    print(f"Mean error:   {metrics['mean_error_km']:.4f} km")
    print(f"Median error: {metrics['median_error_km']:.4f} km")
    print(f"Max error:    {metrics['max_error_km']:.4f} km")
    print(f"Within 0.5 km:{metrics['in_radius_0.5km_pct']:.1f}%")
    print(f"Within 1 km:  {metrics['in_radius_1km_pct']:.1f}%")
    print(f"Within 3 km:  {metrics['in_radius_3km_pct']:.1f}%")
    print(f"Within 5 km:  {metrics['in_radius_5km_pct']:.1f}%")
    print(f"Within 10 km: {metrics['in_radius_10km_pct']:.1f}%")

    return preds, metrics


def predict_sample(abundances: dict) -> tuple[float, float]:
    """
    Predict lat/lon for a single new sample.

    Parameters
    ----------
    abundances : dict
        {species_name: relative_abundance} for as many species as you have.
        Missing species default to 0.0.

    Returns
    -------
    (latitude, longitude) as floats
    """
    pipeline = joblib.load("/home/chandru/binp51/src/ml/mlruns/1/models/m-150112cb0dfd4175b98a23716a7f042b/artifacts/model.pkl")

    # Get expected input columns from fitted zero filter
    FEATURE_COLUMNS = pipeline.named_steps["zeros_filter"]._keep_cols_

    # Build a single-row DataFrame, filling missing species with 0
    row = {col: abundances.get(col, 0.0) for col in FEATURE_COLUMNS}
    X = pd.DataFrame([row], columns=FEATURE_COLUMNS)

    # Predict in meters (EPSG:3006)
    pred = pipeline.predict(X)  # [[x_meters, y_meters]]
    x_meters, y_meters = pred[0]

    # Convert back to lat/lon
    transformer = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x_meters, y_meters)

    return lat, lon


if __name__ == "__main__":
    # Run the blind test set evaluation
    preds, metrics = predict_and_evaluate_test_set()
