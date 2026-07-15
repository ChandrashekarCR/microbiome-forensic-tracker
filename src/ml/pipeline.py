import warnings

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline

from ml.config import config
from ml.evaluation import evaluate_coordinates, evaluate_projected_coordinates
from ml.features import KBestFeatureSelection, LinearModelScaler, GraphLaplacianFeatureEngineer, ZeroColumnFilter, CLRFilter
from ml.mlflow_utils import log_feature_count
from ml.models import TrainTestSplit, DataRoute, BaseSynthesizer

warnings.filterwarnings("ignore", category=RuntimeWarning, module="sklearn.covariance")


# Predict the latitude and longitude together
# We just wrap any model with multiregressor which will predict latitude and longitude both simultaneously
def _wrap_multioutput(estimator):
    if isinstance(estimator, MultiOutputRegressor):
        return estimator
    return MultiOutputRegressor(estimator)


# Build a pipline which is re-usable
def build_modelling_pipeline(estimator, use_k_best: bool = False, 
                             use_network_features: bool = True, 
                             feature_flags: dict = None, 
                             model_family: str = "tree") -> Pipeline:
    """
    Build a reusable pipeline with optional network feature engineering.
    """
    steps = []

    # Select the best features
    if use_k_best:
        steps.append(("k_best_select", KBestFeatureSelection(k=config.feature_engineering.k_best_features)))

    # Feature Engineering toggle switch
    if use_network_features:
        # Default flags if none provided (fallback to CLR‑only)
        if feature_flags is None:
            feature_flags = {}

        # Extract all parameters that GraphLaplacianFeatureEngineer accepts
        # We'll pass the whole dict, but only keys that are in the class's __init__
        valid_keys = [
            "cv_folds", "max_iter", "n_jobs", 
            "n_spectral_features", "min_community_size", 
            "edge_threshold", "eps",
            "use_spectral", "use_global_graph", "use_community"
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
    #previous_step_name = "raw"

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

    # Dictionary to track all feature counts across folds
    all_feature_counts = {}

    cv_splits = get_configured_cv_split(splitter)
    use_meters = config.pipeline_excecution.get("use_cartesian_meters", True)
    strategy = config.pipeline_excecution.get("cv_strategy").lower()
    y_cols = ["X_meters", "Y_meters"] if use_meters else ["latitude", "longitude"]

    for fold, (train_idx, val_idx) in enumerate(cv_splits):
        # 1. Get fold data
        X_train_raw, X_val_raw, y_train_zone, y_val_zone, \
        y_train_coords, y_val_coords = splitter.get_fold_data(train_idx, val_idx)

        # Check if the use meters is switched on or off. If we are using cartesion then we need to train on x,y as cartesion cordinates
        # and not as latitude and longitude
        y_train = y_train_coords[y_cols]

        # Fit preprocessing X_train_raw through zero filtering and clr
        zero_filter = ZeroColumnFilter(
            min_prevalence=config.feature_engineering.min_prevalance,
            min_abd=config.feature_engineering.min_abundance
        )
        X_train_filtered = zero_filter.fit_transform(X_train_raw)
        X_val_filtered = zero_filter.transform(X_val_raw)

        # Apply CLR transform (no fitting needed)
        clr_filter = CLRFilter(delta=config.feature_engineering.delta_value)
        X_train_clean = clr_filter.transform(X_train_filtered)
        X_val_clean = clr_filter.transform(X_val_filtered)

        # Ensure DataFrames with consistent columns
        if not isinstance(X_train_clean, pd.DataFrame):
            cols = zero_filter._keep_cols_  # column names after filtering
            X_train_clean = pd.DataFrame(X_train_clean, columns=cols)
            X_val_clean = pd.DataFrame(X_val_clean, columns=cols)
        
        # Generate in synthetic data in the clean filter space
        if data_route != DataRoute.RAW and synthesizer is not None:
            print("Fitting synthetic data")
            synthesizer.fit(X_train_clean,y_train.reset_index(drop=True))
            syn_X, syn_y = synthesizer.generate(n=n_synthetic)
        
            # Align columns (synthesizer might reorder)
            syn_X = syn_X.reindex(columns=X_train_clean.columns,fill_value=0.0)
            syn_y = syn_y.reindex(columns=y_cols,fill_value=0.0)

            if data_route == DataRoute.SYNTHETIC:
                X_train_final = syn_X.reset_index(drop=True)
                y_train_final = syn_y.reset_index(drop=True)
            else: # Combined  = raw + synthetic
                X_train_final = pd.concat(
                    [X_train_clean.reset_index(drop=True),syn_X],
                    ignore_index=True
                )
                y_train_final = pd.concat(
                    [y_train.reset_index(drop=True),syn_y],
                    ignore_index=True
                )
        else:
            X_train_final = X_train_clean.reset_index(drop=True)
            y_train_final = y_train.reset_index(drop=True)

        # 2. Build pipeline (Create a frsh piepline for each fold)
        pipeline = build_modelling_pipeline(
            clone(estimator), 
            use_network_features=use_network_features, 
            use_k_best=use_k_best, 
            feature_flags=feature_flags, 
            model_family=model_family
        )

        # 3. Fit the models
        pipeline.fit(X_train_final, y_train_final)

        # Log feature counts for this fold using the fitted preprocessing steps
        #stage_counts = log_fold_feature_counts(fold, X_train_final, X_val_clean, pipeline)

        # Store in master dictionary
        #for stage_name, counts in stage_counts.items():
        #    if stage_name not in all_feature_counts:
        #        all_feature_counts[stage_name] = {"train": [], "val": []}
        #    all_feature_counts[stage_name]["train"].append(counts.get("train", 0))
        #    all_feature_counts[stage_name]["val"].append(counts.get("val", 0))

        # 4. Predict on validation
        preds_val = pipeline.predict(X_val_clean)

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
