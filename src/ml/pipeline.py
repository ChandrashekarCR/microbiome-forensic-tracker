import warnings

import numpy as np
from sklearn.base import clone
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline

from ml.config import config
from ml.evaluation import evaluate_coordinates, evaluate_projected_coordinates
from ml.features import CLRFilter, GraphLaplacianFeatureEngineer, KBestFeatureSelection, LinearModelScaler, ZeroColumnFilter
from ml.models import BaseSynthesizer, DataRoute, TrainTestSplit

warnings.filterwarnings("ignore", category=RuntimeWarning, module="sklearn.covariance")


# Predict the latitude and longitude together
# We just wrap any model with multiregressor which will predict latitude and longitude both simultaneously
def _wrap_multioutput(estimator):
    if isinstance(estimator, MultiOutputRegressor):
        return estimator
    return MultiOutputRegressor(estimator)


# Build a pipline which is re-usable
def build_modelling_pipeline(
    estimator, use_k_best: bool = False, use_network_features: bool = True, feature_flags: dict = None, model_family: str = "tree"
) -> Pipeline:
    """
    Build a reusable pipeline with optional network feature engineering.
    """
    steps = []

    steps.append(
        ("prevalence", ZeroColumnFilter(min_prevalence=config.feature_engineering.min_prevalance, min_abd=config.feature_engineering.min_abundance))
    )
    steps.append(("clr", CLRFilter(delta=config.feature_engineering.delta_value)))

    # Select the best features
    # if use_k_best:
    #    steps.append(("k_best_select", KBestFeatureSelection(k=config.feature_engineering.k_best_features)))

    # Feature Engineering toggle switch
    if use_network_features:
        # Default flags if none provided (fallback to CLR‑only)
        if feature_flags is None:
            feature_flags = {}

        # Extract all parameters that GraphLaplacianFeatureEngineer accepts
        # We'll pass the whole dict, but only keys that are in the class's __init__
        valid_keys = [
            "cv_folds",
            "max_iter",
            "n_jobs",
            "n_spectral_features",
            "min_community_size",
            "edge_threshold",
            "eps",
            "use_spectral",
            "use_global_graph",
            "use_community",
        ]
        network_kwargs = {k: v for k, v in feature_flags.items() if k in valid_keys}

        # If any required parameter is missing, fall back to config defaults
        if "cv_folds" not in network_kwargs:
            network_kwargs["cv_folds"] = config.feature_engineering.cv_folds
        if "max_iter" not in network_kwargs:
            network_kwargs["max_iter"] = config.feature_engineering.max_iter

        steps.append(
            (
                "network_features",
                GraphLaplacianFeatureEngineer(**network_kwargs),
            )
        )
        if use_k_best:
            steps.append(("k_best_select_after_network", KBestFeatureSelection(k=config.feature_engineering.k_best_features)))

        # Scaling only linear models
        if model_family == "linear":
            steps.append(("scaler", LinearModelScaler()))

    steps.append(("model", _wrap_multioutput(estimator)))

    return Pipeline(steps)


# There are different ways of splitting the data, but everything generates indcices, we will use accordingly
def get_configured_cv_split(splitter: TrainTestSplit):
    """
    Dynamic CV selector based on the global pipeline execution strategy string
    """
    strategy = config.pipeline_excecution.get("cv_strategy").lower()

    if strategy == "loo":
        return splitter.leave_one_out_split()
    elif strategy == "repeated_kfold":
        return splitter.repeated_zone_data_split()
    elif strategy == "group_kfold":
        return splitter.groupkfold_zone_split()
    elif strategy == "group_kfold_site":
        return splitter.groupkfold_site_split()
    else:
        return splitter.repeated_stratified_zone_data_split()


# Evaluate a single model with cross validation. This function is called in the _rank_models.
def evaluate_model_cv(
    splitter: TrainTestSplit,
    estimator,
    synthesizer: BaseSynthesizer = None,
    data_route: DataRoute = DataRoute.RAW,
    n_synthetic: int = 500,
    use_network_features: bool = False,
    use_k_best: bool = False,
    feature_flags: dict = None,
    model_family: str = "tree",
):

    fold_mekm = []
    fold_mdekm = []
    fold_maxekm = []
    fold_05km = []
    fold_1km = []
    fold_3km = []
    fold_5km = []
    fold_10km = []

    cv_splits = get_configured_cv_split(splitter)
    use_meters = config.pipeline_excecution.get("use_cartesian_meters", True)
    strategy = config.pipeline_excecution.get("cv_strategy").lower()
    y_cols = ["X_meters", "Y_meters"] if use_meters else ["latitude", "longitude"]

    for fold, (train_idx, val_idx) in enumerate(cv_splits):
        # 1. Get fold data
        X_train, X_val, y_train_zone, y_val_zone, y_train_coords, y_val_coords = splitter.get_fold_data(train_idx, val_idx)

        # Check if the use meters is switched on or off. If we are using cartesion then we need to train on x,y as cartesion cordinates
        # and not as latitude and longitude
        y_train = y_train_coords[y_cols]

        # 2. Build pipeline (Create a frsh piepline for each fold)
        pipeline = build_modelling_pipeline(
            clone(estimator), use_network_features=use_network_features, use_k_best=use_k_best, feature_flags=feature_flags, model_family=model_family
        )

        # 3. Fit the models
        pipeline.fit(X_train, y_train)

        # 4. Predict on validation
        preds_val = pipeline.predict(X_val)

        # 5. Custom evaluation script (use projected meters if configured)
        if use_meters:
            metrics = evaluate_projected_coordinates(
                x_true=y_val_coords["X_meters"].values,
                y_true=y_val_coords["Y_meters"].values,
                x_pred=preds_val[:, 0],
                y_pred=preds_val[:, 1],
                zones_true=y_val_zone.values,
            )
        else:
            metrics = evaluate_coordinates(
                y_true_lat=y_val_coords["latitude"].values,
                y_true_lon=y_val_coords["longitude"].values,
                y_pred_lat=preds_val[:, 0],
                y_pred_lon=preds_val[:, 1],
                zones_true=y_val_zone.values,
            )

        # Collect per fold metrics
        fold_mekm.append(metrics["mean_error_km"])
        fold_mdekm.append(metrics["median_error_km"])
        fold_maxekm.append(metrics["max_error_km"])
        fold_05km.append(metrics["in_radius_0.5km_pct"])
        fold_1km.append(metrics["in_radius_1km_pct"])
        fold_3km.append(metrics["in_radius_3km_pct"])
        fold_5km.append(metrics["in_radius_5km_pct"])
        fold_10km.append(metrics["in_radius_10km_pct"])

        print(f"Fold {fold + 1} Mean Distance Error: {metrics['mean_error_km']:.2f} km")

    # Calculate the mean of mean error in km per fold, mean of median, and mean of max error
    # Aggregate
    avg_mekm = float(np.mean(fold_mekm))
    avg_mdekm = float(np.mean(fold_mdekm))
    avg_maxekm = float(np.mean(fold_maxekm))
    avg_05km = float(np.mean(fold_05km))
    avg_1km = float(np.mean(fold_1km))
    avg_3km = float(np.mean(fold_3km))
    avg_5km = float(np.mean(fold_5km))
    avg_10km = float(np.mean(fold_10km))

    print(f"\nCompleted CV with strategy {strategy}. Mean Distance Error: {avg_mekm:.4f}")

    # Final summary of the averaged metrics from the fold for logging
    summary_metrics = {
        "cv_mean_error_km": avg_mekm,
        "cv_median_error_km": avg_mdekm,
        "cv_max_error_km": avg_maxekm,
        "cv_in_radius_0.5km_pct": avg_05km,
        "cv_in_radius_1km_pct": avg_1km,
        "cv_in_radius_3km_pct": avg_3km,
        "cv_in_radius_5km_pct": avg_5km,
        "cv_in_radius_10km_pct": avg_10km,
    }

    return avg_mekm, summary_metrics
