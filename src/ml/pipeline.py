import warnings

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline

from ml.config import config
from ml.evaluation import evaluate_coordinates, evaluate_projected_coordinates
from ml.features import KBestFeatureSelection, LinearModelScaler, MicrobiomeFeatureEngineer, ZeroColumnFilter
from ml.mlflow_utils import log_feature_count
from ml.models import TrainTestSplit

warnings.filterwarnings("ignore", category=RuntimeWarning, module="sklearn.covariance")


# Predict the latitude and longitude together
# We just wrap any model with multiregressor which will predict latitude and longitude both simultaneously
def _wrap_multioutput(estimator):
    if isinstance(estimator, MultiOutputRegressor):
        return estimator
    return MultiOutputRegressor(estimator)


# Build a pipline which is re-usable
def build_pipeline(estimator, use_network_features: bool = True, use_k_best: bool = False, feature_flags: dict = None, model_family: str = "tree"):
    """
    Build a reusable pipeline with optional network feature engineering.
    """
    steps = []

    # Prevalence filter toggle switch
    steps.append(("zeros_filter", ZeroColumnFilter(min_prevalence=config.feature_engineering.min_prevalence)))

    # Select the best features
    if use_k_best:
        steps.append(("k_best_select", KBestFeatureSelection(k=config.feature_engineering.k_best_features)))

    # Feature Engineering toggle switch
    if use_network_features:
        # Default flags if not provieded
        if feature_flags is None:
            feature_flags = {
                "use_clr": True,
                "use_degree": False,
                "use_hub": False,
                "use_edge": False,
                "top_k_edges": config.feature_engineering.top_k_edges,
            }

        steps.append(
            (
                "network_features",
                MicrobiomeFeatureEngineer(
                    cv_folds=config.feature_engineering.cv_folds,
                    max_iter=config.feature_engineering.max_iter,
                    top_k_edges=feature_flags.get("top_k_edges", config.feature_engineering.top_k_edges),
                    use_clr=feature_flags.get("use_clr", True),
                    use_degree=feature_flags.get("use_degree", False),
                    use_hub=feature_flags.get("use_hub", False),
                    use_edge=feature_flags.get("use_edge", False),
                ),
            )
        )
        if use_k_best:
            steps.append(("k_best_select_after_network", KBestFeatureSelection(k=config.feature_engineering.k_best_features)))

        # Scaling only linear models
        if model_family == "linear":
            steps.append(("scaler", LinearModelScaler()))

    steps.append(("model", _wrap_multioutput(estimator)))

    return Pipeline(steps)


def log_fold_feature_counts(fold: int, X_train: pd.DataFrame, X_val: pd.DataFrame, pipeline: Pipeline):
    """
    Log feature counts before/after each preprocessing stage for train and validation data.
    Counts are recorded after applying each fitted transform in the pipeline.
    """
    stage_counts = {}

    def count_after_step(frame: pd.DataFrame, fitted_step):
        transformed = fitted_step.transform(frame)
        if isinstance(transformed, pd.DataFrame):
            transformed = transformed.copy()
            transformed.columns = transformed.columns.map(str)
            transformed = transformed.loc[:, ~transformed.columns.duplicated(keep="first")]
            transformed = transformed.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
            transformed = transformed.astype(np.float32)
            return transformed, transformed.shape[1]
        transformed = np.asarray(transformed)
        return transformed, transformed.shape[1]

    # Log raw input counts
    stage_counts["raw"] = {"train": X_train.shape[1], "val": X_val.shape[1]}
    log_feature_count(f"fold_{fold + 1}.raw.train.n_features", X_train.shape[1], fold)
    log_feature_count(f"fold_{fold + 1}.raw.val.n_features", X_val.shape[1], fold)

    # Track transformed data through pipeline
    current_train = X_train.copy()
    current_val = X_val.copy()

    # Store step names for tracking
    _previous_step_name = "raw"

    for step_name, step_obj in pipeline.steps:
        if step_name == "model":
            break
        if not hasattr(step_obj, "transform"):
            continue

        # Transform data
        current_train, n_train = count_after_step(current_train, step_obj)
        current_val, n_val = count_after_step(current_val, step_obj)

        # Create a clean stage name
        stage_key = f"after_{step_name}"
        stage_counts[stage_key] = {"train": n_train, "val": n_val}

        # Log to MLflow with fold information
        log_feature_count(f"fold_{fold + 1}.{stage_key}.train.n_features", n_train, fold)
        log_feature_count(f"fold_{fold + 1}.{stage_key}.val.n_features", n_val, fold)

        # Print progress for debugging
        # print(f"  Stage '{step_name}': Train={n_train}, Val={n_val} (Δ: {n_train - stage_counts[_previous_step_name]['train']})")

        _previous_step_name = stage_key

    return stage_counts


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
    else:
        return splitter.repeated_stratified_zone_data_split()


# Evaluate a single model with cross validation. This function is called in the _rank_models.
def evaluate_model_cv(
    splitter: TrainTestSplit,
    estimator,
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

    # Dictionary to track all feature counts across folds
    all_feature_counts = {}

    cv_splits = get_configured_cv_split(splitter)
    use_meters = config.pipeline_excecution.get("use_cartesian_meters", True)
    strategy = config.pipeline_excecution.get("cv_strategy").lower()

    for fold, (train_idx, val_idx) in enumerate(cv_splits):
        # 1. Get fold data
        X_train, X_val, y_train_zone, y_val_zone, y_train_coords, y_val_coords = splitter.get_fold_data(train_idx, val_idx)

        # Check if the use meters is switched on or off. If we are using cartesion then we need to train on x,y as cartesion cordinates
        # and not as latitude and longitude
        if use_meters:
            y_train_coords = y_train_coords[["X_meters", "Y_meters"]]
        else:
            y_train_coords = y_train_coords[["latitude", "longitude"]]

        # 2. Build pipeline (Create a frsh piepline for each fold)
        pipeline = build_pipeline(
            clone(estimator), use_network_features=use_network_features, use_k_best=use_k_best, feature_flags=feature_flags, model_family=model_family
        )

        # 3. Fit the models
        pipeline.fit(X_train, y_train_coords)

        # Log feature counts for this fold using the fitted preprocessing steps
        stage_counts = log_fold_feature_counts(fold, X_train, X_val, pipeline)

        # Store in master dictionary
        for stage_name, counts in stage_counts.items():
            if stage_name not in all_feature_counts:
                all_feature_counts[stage_name] = {"train": [], "val": []}
            all_feature_counts[stage_name]["train"].append(counts.get("train", 0))
            all_feature_counts[stage_name]["val"].append(counts.get("val", 0))

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
