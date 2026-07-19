import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone

from ml.config import config
from ml.evaluation import evaluate_projected_coordinates
from ml.models import TrainTestSplit, load_and_prep_data
from ml.pipeline import build_modelling_pipeline
from ml.model_registry import models


# ----------------------------------------------------------------------
# Helper: get a fresh estimator for a given model type
# ----------------------------------------------------------------------
def get_model(model_type):
    """Return a cloned estimator for the given model type."""
    all_models = models.get_baseline_models()
    for m in all_models:
        if m['model_type'] == model_type:
            return clone(m['estimator'])
    raise ValueError(f"Model '{model_type}' not found in registry.")


# ----------------------------------------------------------------------
# 1. Baseline model (NO network features)
# ----------------------------------------------------------------------
def evaluate_baseline_on_test_set(seeds=range(1, 11)):
    """
    Build baseline pipeline (NO network features) for each seed,
    fit on CV set, evaluate on test set, and return metrics.
    """
    print("=" * 60)
    print("Evaluating BASELINE model on test set (10 random splits)")
    print("=" * 60)

    all_metrics = []
    base_estimator = get_model("ExtraTreesRegressor")

    for seed in seeds:
        original_rs = config.data_splitting.random_state
        config.data_splitting.random_state = seed

        config.database.table = "malmo_order"
        df = load_and_prep_data()
        splitter = TrainTestSplit(
            df,
            n_splits=config.data_splitting.n_splits,
            test_size=config.data_splitting.test_size,
        )
        X_cv = splitter.X_cv
        y_cv = splitter.y_cv_coords[["X_meters", "Y_meters"]]
        X_test, y_test_zone, y_test_coords = splitter.get_test_data()
        X_test = X_test.reindex(columns=splitter.X_cv.columns, fill_value=0.0)

        pipeline = build_modelling_pipeline(
            estimator=clone(base_estimator),
            use_network_features=False,
            use_k_best=False,
            feature_flags=None,
            model_family="tree"
        )
        pipeline.fit(X_cv, y_cv)
        preds = pipeline.predict(X_test)

        metrics = evaluate_projected_coordinates(
            x_true=y_test_coords["X_meters"].values,
            y_true=y_test_coords["Y_meters"].values,
            x_pred=preds[:, 0],
            y_pred=preds[:, 1],
            zones_true=y_test_zone.values,
        )
        all_metrics.append(metrics)
        print(f"Seed {seed:2d} | Mean: {metrics['mean_error_km']:.4f} km | "
              f"Median: {metrics['median_error_km']:.4f} km | "
              f"Max: {metrics['max_error_km']:.4f} km")

        config.data_splitting.random_state = original_rs

    # Aggregate all metrics
    mean_errors = [m['mean_error_km'] for m in all_metrics]
    median_errors = [m['median_error_km'] for m in all_metrics]
    max_errors = [m['max_error_km'] for m in all_metrics]

    print("\n" + "=" * 60)
    print("BASELINE SUMMARY (over 10 seeds)")
    print("=" * 60)
    print(f"Mean Error:   {np.mean(mean_errors):.4f} ± {np.std(mean_errors):.4f} km  (range: {np.min(mean_errors):.4f}–{np.max(mean_errors):.4f})")
    print(f"Median Error: {np.mean(median_errors):.4f} ± {np.std(median_errors):.4f} km  (range: {np.min(median_errors):.4f}–{np.max(median_errors):.4f})")
    print(f"Max Error:    {np.mean(max_errors):.4f} ± {np.std(max_errors):.4f} km  (range: {np.min(max_errors):.4f}–{np.max(max_errors):.4f})")

    return all_metrics


# ----------------------------------------------------------------------
# 2. Untuned Feature Engineering model
# ----------------------------------------------------------------------
def evaluate_untuned_fe_on_test_set(seeds=range(1, 11)):
    """
    Evaluate the UNTUNED FE pipeline (saved from run_stage2_fe_network)
    on the test set across 10 random seeds.
    """
    print("\n" + "=" * 60)
    print("Evaluating UNTUNED FE model on test set (10 random splits)")
    print("=" * 60)

    pipeline = joblib.load("/home/chandru/binp51/src/ml/fe_model_group_kfold.joblib")
    all_metrics = []

    for seed in seeds:
        original_rs = config.data_splitting.random_state
        config.data_splitting.random_state = seed

        config.database.table = "malmo_order"
        df = load_and_prep_data()
        splitter = TrainTestSplit(
            df,
            n_splits=config.data_splitting.n_splits,
            test_size=config.data_splitting.test_size,
        )
        X_test, y_test_zone, y_test_coords = splitter.get_test_data()
        X_test = X_test.reindex(columns=splitter.X_cv.columns, fill_value=0.0)

        preds = pipeline.predict(X_test)
        metrics = evaluate_projected_coordinates(
            x_true=y_test_coords["X_meters"].values,
            y_true=y_test_coords["Y_meters"].values,
            x_pred=preds[:, 0],
            y_pred=preds[:, 1],
            zones_true=y_test_zone.values,
        )
        all_metrics.append(metrics)
        print(f"Seed {seed:2d} | Mean: {metrics['mean_error_km']:.4f} km | "
              f"Median: {metrics['median_error_km']:.4f} km | "
              f"Max: {metrics['max_error_km']:.4f} km")

        config.data_splitting.random_state = original_rs

    mean_errors = [m['mean_error_km'] for m in all_metrics]
    median_errors = [m['median_error_km'] for m in all_metrics]
    max_errors = [m['max_error_km'] for m in all_metrics]

    print("\n" + "=" * 60)
    print("UNTUNED FE SUMMARY (over 10 seeds)")
    print("=" * 60)
    print(f"Mean Error:   {np.mean(mean_errors):.4f} ± {np.std(mean_errors):.4f} km  (range: {np.min(mean_errors):.4f}–{np.max(mean_errors):.4f})")
    print(f"Median Error: {np.mean(median_errors):.4f} ± {np.std(median_errors):.4f} km  (range: {np.min(median_errors):.4f}–{np.max(median_errors):.4f})")
    print(f"Max Error:    {np.mean(max_errors):.4f} ± {np.std(max_errors):.4f} km  (range: {np.min(max_errors):.4f}–{np.max(max_errors):.4f})")

    return all_metrics


# ----------------------------------------------------------------------
# 3. Tuned Feature Engineering model (final pipeline)
# ----------------------------------------------------------------------
def evaluate_tuned_fe_on_test_set(seeds=range(1, 11)):
    """
    Evaluate the TUNED FE pipeline (final_tuned_model_group_kfold.joblib)
    on the test set across 10 random seeds.
    """
    print("\n" + "=" * 60)
    print("Evaluating TUNED FE model on test set (10 random splits)")
    print("=" * 60)

    pipeline = joblib.load("/home/chandru/binp51/src/ml/final_tuned_model_group_kfold.joblib")
    all_metrics = []

    for seed in seeds:
        original_rs = config.data_splitting.random_state
        config.data_splitting.random_state = seed

        config.database.table = "malmo_order"
        df = load_and_prep_data()
        splitter = TrainTestSplit(
            df,
            n_splits=config.data_splitting.n_splits,
            test_size=config.data_splitting.test_size,
        )
        X_test, y_test_zone, y_test_coords = splitter.get_test_data()
        X_test = X_test.reindex(columns=splitter.X_cv.columns, fill_value=0.0)

        preds = pipeline.predict(X_test)
        metrics = evaluate_projected_coordinates(
            x_true=y_test_coords["X_meters"].values,
            y_true=y_test_coords["Y_meters"].values,
            x_pred=preds[:, 0],
            y_pred=preds[:, 1],
            zones_true=y_test_zone.values,
        )
        all_metrics.append(metrics)
        print(f"Seed {seed:2d} | Mean: {metrics['mean_error_km']:.4f} km | "
              f"Median: {metrics['median_error_km']:.4f} km | "
              f"Max: {metrics['max_error_km']:.4f} km")

        config.data_splitting.random_state = original_rs

    mean_errors = [m['mean_error_km'] for m in all_metrics]
    median_errors = [m['median_error_km'] for m in all_metrics]
    max_errors = [m['max_error_km'] for m in all_metrics]

    print("\n" + "=" * 60)
    print("TUNED FE SUMMARY (over 10 seeds)")
    print("=" * 60)
    print(f"Mean Error:   {np.mean(mean_errors):.4f} ± {np.std(mean_errors):.4f} km  (range: {np.min(mean_errors):.4f}–{np.max(mean_errors):.4f})")
    print(f"Median Error: {np.mean(median_errors):.4f} ± {np.std(median_errors):.4f} km  (range: {np.min(median_errors):.4f}–{np.max(median_errors):.4f})")
    print(f"Max Error:    {np.mean(max_errors):.4f} ± {np.std(max_errors):.4f} km  (range: {np.min(max_errors):.4f}–{np.max(max_errors):.4f})")

    return all_metrics


# ----------------------------------------------------------------------
# 4. Run all three and compare
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Run evaluations
    baseline_metrics = evaluate_baseline_on_test_set(seeds=range(1, 11))
    untuned_fe_metrics = evaluate_untuned_fe_on_test_set(seeds=range(1, 11))
    tuned_fe_metrics = evaluate_tuned_fe_on_test_set(seeds=range(1, 11))

    # Extract all metrics
    baseline_mean = [m['mean_error_km'] for m in baseline_metrics]
    baseline_median = [m['median_error_km'] for m in baseline_metrics]
    baseline_max = [m['max_error_km'] for m in baseline_metrics]

    untuned_mean = [m['mean_error_km'] for m in untuned_fe_metrics]
    untuned_median = [m['median_error_km'] for m in untuned_fe_metrics]
    untuned_max = [m['max_error_km'] for m in untuned_fe_metrics]

    tuned_mean = [m['mean_error_km'] for m in tuned_fe_metrics]
    tuned_median = [m['median_error_km'] for m in tuned_fe_metrics]
    tuned_max = [m['max_error_km'] for m in tuned_fe_metrics]

    print("\n" + "=" * 60)
    print("FINAL THREE‑WAY COMPARISON (over 10 seeds)")
    print("=" * 60)
    print(f"{'Model':<20} {'Mean Error (km)':<25} {'Median Error (km)':<25} {'Max Error (km)':<25}")
    print("-" * 100)
    print(f"{'Baseline (no FE)':<20} {np.mean(baseline_mean):.4f} ± {np.std(baseline_mean):.4f}  "
          f"{np.mean(baseline_median):.4f} ± {np.std(baseline_median):.4f}  "
          f"{np.mean(baseline_max):.4f} ± {np.std(baseline_max):.4f}")
    print(f"{'Untuned FE':<20} {np.mean(untuned_mean):.4f} ± {np.std(untuned_mean):.4f}  "
          f"{np.mean(untuned_median):.4f} ± {np.std(untuned_median):.4f}  "
          f"{np.mean(untuned_max):.4f} ± {np.std(untuned_max):.4f}")
    print(f"{'Tuned FE (Final)':<20} {np.mean(tuned_mean):.4f} ± {np.std(tuned_mean):.4f}  "
          f"{np.mean(tuned_median):.4f} ± {np.std(tuned_median):.4f}  "
          f"{np.mean(tuned_max):.4f} ± {np.std(tuned_max):.4f}")

    print("\n" + "=" * 60)
    print("IMPROVEMENTS")
    print("=" * 60)
    print(f"FE Improvement (untuned): Mean: {np.mean(baseline_mean) - np.mean(untuned_mean):.4f} km")
    print(f"Tuning Improvement:       Mean: {np.mean(untuned_mean) - np.mean(tuned_mean):.4f} km")
    print(f"Total Improvement:        Mean: {np.mean(baseline_mean) - np.mean(tuned_mean):.4f} km")