import numpy as np
from omegaconf import ListConfig
from sklearn.base import clone
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
import mlflow

from ml.config import config
from ml.evaluation import evaluate_coordinates, evaluate_projected_coordinates
from ml.features import MicrobiomeFeatureEngineer, ZeroColumnFilter
from ml.model_registry import models as model_registry
from ml.models import TrainTestSplit, load_and_prep_data
from ml.mlflow_utils import start_run, log_model_params, log_model_metrics

import warnings
warnings.filterwarnings('ignore', category=RuntimeWarning, module='sklearn.covariance')

# Predict the latitude and longitude together
# We just wrap any model with multiregressor which will predict latitude and longitude both simultaneously
def _wrap_multioutput(estimator):
    if isinstance(estimator, MultiOutputRegressor):
        return estimator
    return MultiOutputRegressor(estimator)

# Build a pipline which is re-usable
def build_pipeline(estimator, use_network_features: bool = True):
    """
    Build a reusable pipeline with optional network feature engineering.
    """
    steps = []

    # Prevalence filter toggle switch
    steps.append(("zeros_filter", ZeroColumnFilter(min_prevalence=config.feature_engineering.min_prevalence)))

    # Feature Engineering toggle switch
    if use_network_features:
        steps.append(
            (
                "network_features",
                MicrobiomeFeatureEngineer(
                    cv_folds=config.feature_engineering.cv_folds,
                    max_iter=config.feature_engineering.max_iter,
                    top_k_edges=config.feature_engineering.top_k_edges,
                ),
            )
        )

    steps.append(("model", _wrap_multioutput(estimator)))

    return Pipeline(steps)

# There are different ways of splitting the data, but everything generates indcices, we will use accordingly
def _get_configured_cv_split(splitter: TrainTestSplit):
    """
    Dynamic CV selector based on the global pipeline execution strategy string
    """
    strategy = config.pipeline_excecution.get("cv_strategy").lower()

    if strategy == "loo":
        return splitter.leave_one_out_split()
    elif strategy == "repeated_kfold":
        return splitter.repeated_zone_data_split()
    else:
        return splitter.repeated_stratified_zone_data_split()

# Evaluate a single model with cross validation. This function is called in the _rank_models.
def evaluate_model_cv(splitter: TrainTestSplit, estimator, use_network_features: bool):
    fold_mekm = []
    fold_mdekm = []
    fold_maxekm = []
    fold_05km = []
    fold_1km = []
    fold_3km = []
    fold_5km = []
    fold_10km = []

    cv_splits = _get_configured_cv_split(splitter)
    use_meters = config.pipeline_excecution.get("use_cartesian_meters", True)
    strategy = config.pipeline_excecution.get("cv_strategy").lower()

    for fold, (train_idx, val_idx) in enumerate(cv_splits):

        # 1. Get fold data
        X_train, X_val, y_train_zone, y_val_zone, y_train_coords, y_val_coords = splitter.get_fold_data(train_idx, val_idx)

        # Check if the use meters is switched on or off. If we are using cartesion then we need to train on x,y as cartesion cordinates
        # and not as latitude and longitude
        if use_meters:
            y_train_coords = y_train_coords[['X_meters','Y_meters']]
        else:
            y_train_coords = y_train_coords[['latitude','longitude']]

        # 2. Build pipeline (Create a frsh piepline for each fold)
        pipeline = build_pipeline(clone(estimator), use_network_features=use_network_features)

        # 3. Fit the models
        pipeline.fit(X_train, y_train_coords)

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


        print(f"Fold {fold + 1} Mean Distance Error: {metrics["mean_error_km"]:.2f} km")
    
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

    return avg_mekm , summary_metrics


# Use all the models mentioned and evaluate each one individually on the train and validation dataset.
# This is the main part of the machine learning architecture, becuase this ranks the models and is called in
# in the run multistage selections
def _rank_models(splitter: TrainTestSplit, model_defs: list, use_network_features: bool, top_k: int = 5):
    
    # Store the results for each model
    results = []
    
    for model_def in model_defs:
        model_name = model_def["name"]
        estimator = model_def["estimator"]

        # Start a separate run for each model
        with start_run(run_name=f"stage1_{model_name}") as run:
            # Log things like stage, network features, what ever is important
            mlflow.set_tag("stage1", "baseline")
            mlflow.set_tag("model_family",model_def.get("family","unknown"))
            mlflow.set_tag("use_network_features",str(use_network_features))

            # Log model params
            if hasattr(estimator,'get_params'):
                mlflow.log_params(estimator.get_params())
            
            print(f"\nEvaluating {model_name} (network_features={use_network_features})")
            
            # Evaluate
            avg_mekm, summary_metrics = evaluate_model_cv(splitter, estimator, use_network_features=use_network_features)


            # Log the average summary metrics
            log_model_metrics(metrics=summary_metrics)

            results.append(
                {
                    "name": model_name,
                    "model_type": model_def.get("model_type"),
                    "estimator": estimator,
                    "avg_mekm": avg_mekm,
                }
            )

    results.sort(key=lambda x: x["avg_mekm"])
    return results[:top_k], results


def _make_haversine_scorer():
    def _scorer(estimator, X, y):
        preds = estimator.predict(X)
        metrics = evaluate_coordinates(
            y_true_lat=y["latitude"].values,
            y_true_lon=y["longitude"].values,
            y_pred_lat=preds[:, 0],
            y_pred_lon=preds[:, 1],
        )
        return -metrics["mean_error_km"]

    return _scorer


# The model which passes through all the filtering criteria is made to be tuned with all the hyperparameters.
def _tune_top_model(splitter: TrainTestSplit, model_def: dict):
    model_type = model_def.get("model_type")
    tuning_cfg = config.stage_3.grids.get(model_type) if "stage_3" in config else None
    if not tuning_cfg:
        print(f"No tuning grid found for {model_type}. Skipping tuning.")
        return build_pipeline(model_def["estimator"], use_network_features=True)

    print(f"\nSTAGE 3: {model_def['name']} (feature engineering + hyperparameter tuning)")

    pipeline = build_pipeline(model_def["estimator"], use_network_features=True)

    param_distributions = {}
    for k, v in tuning_cfg.items():
        if isinstance(v, ListConfig):
            param_distributions[f"model__estimator__{k}"] = list(v)
        else:
            param_distributions[f"model__estimator__{k}"] = v

    min_class_count = splitter.y_cv_zone.value_counts().min()
    requested_folds = int(config.stage_3.cv_folds)
    cv_folds = max(2, min(requested_folds, int(min_class_count)))

    if cv_folds < requested_folds:
        print(f"Reducing stage_3 cv_folds from {requested_folds} to {cv_folds} due to small class counts (min={min_class_count}).")

    cv = StratifiedKFold(
        n_splits=cv_folds,
        shuffle=True,
        random_state=config.stage_3.random_state,
    ).split(splitter.X_cv, splitter.y_cv_zone)

    search = RandomizedSearchCV(
        pipeline,
        param_distributions=param_distributions,
        n_iter=config.stage_3.n_iter,
        scoring=_make_haversine_scorer(),
        cv=cv,
        random_state=config.stage_3.random_state,
        n_jobs=-1,
        verbose=1,
    )

    search.fit(splitter.X_cv, splitter.y_cv_coords)
    print(f"\nStage 3 complete for {model_type}")
    print(f"Best params for {model_type}: {search.best_params_}")
    print(f"Best CV score (negative mean error): {search.best_score_:.4f}")

    return search.best_estimator_


def run_multistage_selection(df, top_k: int = 2):
    """
    STAGE 1: Baseline model ranking.
    STAGE 2: Re-evaluate top K models with feature engineering.
    STAGE 3: Best model with feature engineering + hyperparameter tuning.
    """

    # Pass in the dataframe, number of split and test size
    splitter = TrainTestSplit(
        df,
        n_splits=config.data_splitting.n_splits,
        test_size=config.data_splitting.test_size,
    )

    print("\nSTAGE 1: Baseline model ranking")
    stage1_models = model_registry.get_baseline_models()
    top_stage1, stage1_results = _rank_models(splitter, stage1_models, use_network_features=False, top_k=top_k)

    print("\nStage 1 Results (Top Models):")
    for r in top_stage1:
        print(f"{r['name']}: {r['avg_mekm']:.4f} km")

    #print("\nSTAGE 2: Re-evaluate with top K models (feature engineering)")
    #top_stage2, stage2_results = _rank_models(splitter, top_stage1, use_network_features=True, top_k=1)
#
    #best_model_def = top_stage2[0]
    #print("\nStage 2 Best Model:")
    #print(f"{best_model_def['name']}: {best_model_def['avg_mae']:.4f} km")
#
    #tuned_pipeline = _tune_top_model(splitter, best_model_def)

    #X_test, y_test_zone, y_test_coords = splitter.get_test_data()
    #test_preds = tuned_pipeline.predict(X_test)
    #test_metrics = evaluate_coordinates(
    #    y_true_lat=y_test_coords["latitude"].values,
    #    y_true_lon=y_test_coords["longitude"].values,
    #    y_pred_lat=test_preds[:, 0],
    #    y_pred_lon=test_preds[:, 1],
    #    zones_true=y_test_zone.values,
    #)
#
    #print("\nSTAGE 3 Final Test Evaluation (tuned model):")
    #for metric, value in test_metrics.items():
    #    print(metric, value)
#
    #return {
    #    "stage1_results": stage1_results,
    #    "stage2_results": stage2_results,
    #    "test_metrics": test_metrics,
    #    "best_model": best_model_def,
    #}


if __name__ == "__main__":
    print("Loading data...")
    df = load_and_prep_data()

    print("\n========== MULTI-STAGE MODEL SELECTION ==========")
    run_multistage_selection(df, top_k=2)
