import mlflow
import numpy as np
from sklearn.base import clone
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline

from ml.features import ZeroColumnFilter, MicrobiomeFeatureEngineer
from ml.models import load_and_prep_data, TrainTestSplit
from ml.model_registry import models as model_registry
from ml.config import config
from ml.evaluation import evaluate_coordinates


def _wrap_multioutput(estimator):
    if isinstance(estimator, MultiOutputRegressor):
        return estimator
    return MultiOutputRegressor(estimator)


def build_pipeline(estimator, use_network_features: bool = True):
    """
    Build a reusable pipeline with optional network feature engineering.
    """
    steps = []

    steps.append(("zeros_filter", ZeroColumnFilter(min_prevalence=config.feature_engineering.min_prevalence)))

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


def _evaluate_model_cv(splitter: TrainTestSplit, estimator, use_network_features: bool):
    fold_scores = []

    for fold, (train_idx, val_idx) in enumerate(splitter.stratifed_zone_data_split()):
        print(f"Processing Fold {fold + 1}/{splitter.n_splits}")

        # 1. Get fold data
        X_train, X_val, y_train_zone, y_val_zone, y_train_coords, y_val_coords = splitter.get_fold_data(
            train_idx, val_idx
        )

        # 2. Build pipeline (Create a frsh piepline for each fold)
        pipeline = build_pipeline(clone(estimator), use_network_features=use_network_features)

        # 3. Fit the models
        pipeline.fit(X_train, y_train_coords)

        # 4. Predict on validation
        preds_val = pipeline.predict(X_val)
            
        # 5. Custom evaluation script
        metrics = evaluate_coordinates(
            y_true_lat=y_val_coords["latitude"].values,
            y_true_lon=y_val_coords["longitude"].values,
            y_pred_lat=preds_val[:, 0],
            y_pred_lon=preds_val[:, 1],
            zones_true=y_val_zone.values,
        )

        fold_mae = metrics["mean_error_km"]
        fold_scores.append(fold_mae)
            
        print(f"Fold {fold+1} Mean Haversine Error: {fold_mae:.2f} km")
            
        # Log all your custom metrics for this fold
        for k, v in metrics.items():
            mlflow.log_metric(f"fold_{fold+1}_{k}", v)
        
    # 6. Log Overall CV Metrics
    avg_mae = np.mean(fold_scores)
    print(f"\nCompleted Strategy CV. Average Haversine Error: {avg_mae:.4f}")

    return float(avg_mae)


def _rank_models(splitter: TrainTestSplit, model_defs: list, use_network_features: bool, top_k: int = 5):
    results = []
    for model_def in model_defs:
        model_name = model_def["name"]
        estimator = model_def["estimator"]
        print(f"\nEvaluating {model_name} (network_features={use_network_features})")
        avg_mae = _evaluate_model_cv(splitter, estimator, use_network_features=use_network_features)
        results.append({
            "name": model_name,
            "model_type": model_def.get("model_type"),
            "estimator": estimator,
            "avg_mae": avg_mae,
        })

    results.sort(key=lambda x: x["avg_mae"])
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


def _tune_top_model(splitter: TrainTestSplit, model_def: dict):
    model_type = model_def.get("model_type")
    tuning_cfg = config.stage_3.grids.get(model_type) if "stage_3" in config else None
    if not tuning_cfg:
        print(f"No tuning grid found for {model_type}. Skipping tuning.")
        return build_pipeline(model_def["estimator"], use_network_features=True)

    pipeline = build_pipeline(model_def["estimator"], use_network_features=True)

    param_distributions = {f"model__estimator__{k}": v for k, v in tuning_cfg.items()}
    cv = StratifiedKFold(
        n_splits=config.stage_3.cv_folds,
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
    print(f"Best params for {model_type}: {search.best_params_}")
    print(f"Best CV score (negative mean error): {search.best_score_:.4f}")

    return search.best_estimator_


def run_multistage_selection(df, top_k: int = 5, use_mlflow: bool = False):
    """
    Stage 1: baseline models (no network features) -> select top K.
    Stage 2: add network features on top K -> select best.
    Stage 3: tune best model with network features -> evaluate on holdout test.
    """
    if use_mlflow:
        mlflow.set_experiment(config.mlflow.experiment_name)

    splitter = TrainTestSplit(
        df,
        n_splits=config.data_splitting.n_splits,
        test_size=config.data_splitting.test_size,
    )

    stage1_models = model_registry.get_baseline_models()
    top_stage1, stage1_results = _rank_models(
        splitter, stage1_models, use_network_features=False, top_k=top_k
    )

    print("\nStage 1 Results (Top Models):")
    for r in top_stage1:
        print(f"{r['name']}: {r['avg_mae']:.4f} km")

    top_stage2, stage2_results = _rank_models(
        splitter, top_stage1, use_network_features=True, top_k=1
    )

    best_model_def = top_stage2[0]
    print("\nStage 2 Best Model:")
    print(f"{best_model_def['name']}: {best_model_def['avg_mae']:.4f} km")

    tuned_pipeline = _tune_top_model(splitter, best_model_def)

    X_test, y_test_zone, y_test_coords = splitter.get_test_data()
    test_preds = tuned_pipeline.predict(X_test)
    test_metrics = evaluate_coordinates(
        y_true_lat=y_test_coords["latitude"].values,
        y_true_lon=y_test_coords["longitude"].values,
        y_pred_lat=test_preds[:, 0],
        y_pred_lon=test_preds[:, 1],
        zones_true=y_test_zone.values,
    )

    print("\nFinal Test Evaluation (Tuned Model):")
    for metric, value in test_metrics.items():
        print(metric, value)

    return {
        "stage1_results": stage1_results,
        "stage2_results": stage2_results,
        "test_metrics": test_metrics,
        "best_model": best_model_def,
    }

if __name__ == "__main__":
    print("Loading data...")
    df = load_and_prep_data()
    
    print("\n========== MULTI-STAGE MODEL SELECTION ==========")
    run_multistage_selection(df, top_k=5, use_mlflow=False)


