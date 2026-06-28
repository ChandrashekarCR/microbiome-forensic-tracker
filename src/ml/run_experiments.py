"""
Comprehensive MLflow experiment orchestration script.
Runs three stages of experiments:
  1. Taxonomy baseline: XGBoost only (no feature engineering) across taxonomic levels
  2. Feature engineering variants: Network features + RFE combinations with top taxonomy
  3. Final tuning: Full multistage pipeline with hyperparameter tuning
"""

import time

import mlflow
import mlflow.sklearn

from ml.config import config
from ml.mlflow_utils import log_model_metrics, log_model_params, start_run
from ml.model_registry import models as model_registry
from ml.models import TrainTestSplit, load_and_prep_data
from ml.pipeline import _rank_models, evaluate_model_cv

TAXONOMY_TABLES = {
    "phylum": "malmo_phylum",
    "class": "malmo_class",
    "order": "malmo_order",
    "family": "malmo_family",
    "genus": "malmo_genus",
    "species": "malmo_species",
}

# Feature engineering variants: define which network features to enable
# Each variant is (name, clr, degree, hub)
FE_VARIANTS = [
    ("clr_only", True, False, False),
    ("clr_degree", True, True, False),
    ("clr_hub", True, False, True),
    ("clr_degree_hub", True, True, True),
    ("degree_only", False, True, False),
    ("hub_only", False, False, True),
]

# STAGE 1: 


# STAGE 2: Taxonomy Baseline

def run_stage2_taxonomy_baseline(model_type: str = "XGBoost"):
    """
    Experiment 1: Determine which taxonomy level provides best geolocation signal.
    Uses ONLY XGBoost baseline (no feature engineering, no hyperparameter tuning).
    """
    print(f"STAGE 1: Taxonomy Baseline {model_type} (no feature engineering, no hyperparameter tuning)")

    stage1_results = {}

    # Get the baseline models from the model registry
    all_models = [m for m in model_registry.get_baseline_models()]

    if model_type:
        selected_model = next((m for m in all_models if m["model_type"] == model_type), None)
        if selected_model is None:
            available = [m["model_type"] for m in all_models]
            raise ValueError(f"Model '{model_type}' not enabled. Available: {available}")
    else:
        selected_model = all_models[0]  # Use first enabled model
        model_type = selected_model["model_type"]
    
    model_family = selected_model["family"]
    
    print(f"Using model:{model_type}, family: {model_family}")

    for level, table in TAXONOMY_TABLES.items():
        print(f"\nRunning taxonomy level: {level} (table: {table})")

        # Override config to load from correct table
        config.database.table = table

        # Load data for this taxonomy level
        df = load_and_prep_data()
        print(f"Loaded {len(df)} samples with {df.shape[1] - 3} taxa (after sample_id, zone, coords)")

        # Create train/test split
        splitter = TrainTestSplit(
            df,
            n_splits=config.data_splitting.n_splits,
            test_size=config.data_splitting.test_size,
        )

        # Create MLflow run
        run_name = f"stage1_{model_type}_{level}_{int(time.time())}"
        with start_run(run_name=run_name):
            # === TAGS ===
            mlflow.set_tag("stage", "stage1_taxonomy_baseline")
            mlflow.set_tag("taxonomy_level", level)
            mlflow.set_tag("model_type", model_type)  # e.g., "RandomForest"
            mlflow.set_tag("model_family", model_family)  # e.g., "tree"
            mlflow.set_tag("use_network_features", "False")
            mlflow.set_tag("use_k_best", "False")
            mlflow.set_tag("use_rfe", "False")
            
            # === PARAMETERS ===
            mlflow.log_params({
                "taxonomy_table": table,
                "model_type": model_type,
                "model_family": model_family,
                "n_samples": len(df),
                "cv_strategy": config.pipeline_excecution.get("cv_strategy"),
                "use_meters": config.pipeline_excecution.get("use_cartesian_meters"),
            })

            # Log XGBoost model hyperparameters
            log_model_params(selected_model["estimator"])

            # Evaluate the model across CV folds
            print(f"Evaluating {selected_model['model_type']} with {config.data_splitting.n_splits} splits...")
            avg_mekm, summary_metrics = evaluate_model_cv(splitter, selected_model["estimator"], use_network_features=False, use_k_best=False, feature_flags=None)

            # Log evaluation metrics
            log_model_metrics(metrics=summary_metrics)

            # Store result
            stage1_results[level] = {
                "model_name": selected_model["model_type"],
                "avg_mekm": avg_mekm,
                "metrics": summary_metrics,
                "run_id": mlflow.active_run().info.run_id,
            }

            print(f"Mean error: {avg_mekm:.4f} km")

    # Print summary
    print("Experiment 1 Summary:")
    sorted_results = sorted(stage1_results.items(), key=lambda x: x[1]["avg_mekm"])
    for i, (level, res) in enumerate(sorted_results, 1):
        print(f"{i}. {level:12} - {res['avg_mekm']:8.4f} km (run_id: {res['run_id'][:8]})")

    # Return best taxonomy level for stage 2
    best_level = sorted_results[0][0]
    print(f"Best Taxonomy Level: {best_level}")

    return best_level, stage1_results


# ============================================================================
# STAGE 2: Feature Engineering Variants
# ============================================================================
def run_stage2_feature_engineering(taxonomy_level: str):
    """
    Experiment 2: Given the best taxonomy level, test feature engineering variants.
    Tests network feature combinations + RFE on/off.
    """
    print(f"STAGE 2: Feature Engineering Variants (taxonomy: {taxonomy_level}), no hyperparameter tuning, only XGBoost")

    # Load data for best taxonomy level
    config.database.table = TAXONOMY_TABLES[taxonomy_level]
    df = load_and_prep_data()

    splitter = TrainTestSplit(
        df,
        n_splits=config.data_splitting.n_splits,
        test_size=config.data_splitting.test_size,
    )

    # Get XGBoost model
    xgb_models = [m for m in model_registry.get_baseline_models() if m["model_type"] == "XGBoost"]
    if not xgb_models:
        raise ValueError("XGBoost model not found in registry")
    xgb_def = xgb_models[0]

    stage2_results = {}

    # Generate ALL combinations of feature flags
    # This creates 16 combinations (2^4)
    feature_combinations = [
        # (use_clr, use_degree, use_hub, use_edge)
        (True, False, False, False),  # CLR only
        (False, True, False, False),  # Degree only
        (False, False, True, False),  # Hub only
        (False, False, False, True),  # Edge only
        #        (True, True, False, False),    # CLR + Degree
        #        (True, False, True, False),    # CLR + Hub
        #        (True, False, False, True),    # CLR + Edge
        #        (False, True, True, False),    # Degree + Hub
        #        (False, True, False, True),    # Degree + Edge
        #        (False, False, True, True),    # Hub + Edge
        #        (True, True, True, False),     # CLR + Degree + Hub
        #        (True, True, False, True),     # CLR + Degree + Edge
        #        (True, False, True, True),     # CLR + Hub + Edge
        #        (False, True, True, True),     # Degree + Hub + Edge
        #        (True, True, True, True),      # ALL features
    ]

    # Test 1: Network feature variants
    for use_clr, use_degree, use_hub, use_edge in feature_combinations:
        # Generate a descriptive name
        fe_name_parts = []
        if use_clr:
            fe_name_parts.append("CLR")
        if use_degree:
            fe_name_parts.append("Deg")
        if use_hub:
            fe_name_parts.append("Hub")
        if use_edge:
            fe_name_parts.append("Edge")
        fe_name = "_".join(fe_name_parts) if fe_name_parts else "None"

        print(f"\nVariant: {fe_name}")
        print(f"Flags: CLR={use_clr}, Deg={use_degree}, Hub={use_hub}, Edge={use_edge}")

        run_name = f"stage2_fe_{fe_name}_{taxonomy_level}_{int(time.time())}"

        with start_run(run_name=run_name):
            # === TAGS ===
            mlflow.set_tag("stage", "stage2_feature_engineering")
            mlflow.set_tag("taxonomy_level", taxonomy_level)
            mlflow.set_tag("fe_variant", fe_name)
            mlflow.set_tag("fe_type", "feature_combination")
            mlflow.set_tag("model_type", "XGBoost")

            # === FEATURE FLAG TAGS ===
            mlflow.set_tag("use_clr", str(use_clr))
            mlflow.set_tag("use_degree", str(use_degree))
            mlflow.set_tag("use_hub", str(use_hub))
            mlflow.set_tag("use_edge", str(use_edge))

            # === PARAMETERS ===
            mlflow.log_params(
                {
                    "fe_variant": fe_name,
                    "use_clr": use_clr,
                    "use_degree": use_degree,
                    "use_hub": use_hub,
                    "use_edge": use_edge,
                    "top_k_edges": config.feature_engineering.top_k_edges,
                    "model_type": "XGBoost",
                    "taxonomy_level": taxonomy_level,
                    "cv_strategy": config.pipeline_excecution.get("cv_strategy"),
                    "use_meters": config.pipeline_excecution.get("use_cartesian_meters"),
                }
            )

            # Log XGBoost parameters
            log_model_params(xgb_def["estimator"])

            # === EVALUATE ===
            feature_config = {
                "use_clr": use_clr,
                "use_degree": use_degree,
                "use_hub": use_hub,
                "use_edge": use_edge,
                "top_k_edges": config.feature_engineering.top_k_edges,
            }

            avg_mekm, summary_metrics = evaluate_model_cv(
                splitter=splitter,
                estimator=xgb_def["estimator"],
                use_network_features=True,
                use_k_best=True,
                feature_flags=feature_config,
            )

            # Log metrics
            log_model_metrics(metrics=summary_metrics)

            # Store result
            stage2_results[fe_name] = {
                "fe_type": "feature_combination",
                "fe_variant": fe_name,
                "use_clr": use_clr,
                "use_degree": use_degree,
                "use_hub": use_hub,
                "use_edge": use_edge,
                "avg_mekm": avg_mekm,
                "run_id": mlflow.active_run().info.run_id,
            }

            print(f"      Mean error: {avg_mekm:.4f} km")

    # === PRINT SUMMARY ===
    print("\n" + "=" * 80)
    print("STAGE 2 SUMMARY - ALL FEATURE COMBINATIONS")
    print("=" * 80)

    sorted_results = sorted(stage2_results.items(), key=lambda x: x[1]["avg_mekm"])

    # Create a formatted table
    print(f"\n{'Rank':<6} {'Variant':<25} {'CLR':<6} {'Deg':<6} {'Hub':<6} {'Edge':<6} {'Error (km)':<12} {'Run ID':<10}")
    print("-" * 90)

    for i, (variant, res) in enumerate(sorted_results, 1):
        clr = "✓" if res["use_clr"] else "✗"
        deg = "✓" if res["use_degree"] else "✗"
        hub = "✓" if res["use_hub"] else "✗"
        edge = "✓" if res["use_edge"] else "✗"
        run_id_short = res["run_id"][:8] if "run_id" in res else "N/A"
        print(f"{i:<6} {variant:<25} {clr:<6} {deg:<6} {hub:<6} {edge:<6} {res['avg_mekm']:<12.4f} {run_id_short}")

    # Find best variant
    best_variant = sorted_results[0][0]
    best_error = sorted_results[0][1]["avg_mekm"]

    print("\n" + "=" * 80)
    print(f"✓ BEST FEATURE ENGINEERING: {best_variant}")
    print(f"  Mean error: {best_error:.4f} km")
    print(
        f"  Flags: CLR={sorted_results[0][1]['use_clr']}, "
        f"Deg={sorted_results[0][1]['use_degree']}, "
        f"Hub={sorted_results[0][1]['use_hub']}, "
        f"Edge={sorted_results[0][1]['use_edge']}"
    )
    print("=" * 80)

    return best_variant, stage2_results


# ============================================================================
# STAGE 3: Full Multistage Pipeline + Hyperparameter Tuning
# ============================================================================
def run_stage3_final_tuning(taxonomy_level: str, fe_variant: str):
    """
    Experiment 3: Full pipeline with all models + feature engineering + hyperparameter tuning.
    Selects and saves the best model.
    """
    print("\n" + "=" * 80)
    print("STAGE 3: FULL MULTISTAGE PIPELINE + HYPERPARAMETER TUNING")
    print(f"         Taxonomy: {taxonomy_level}, FE: {fe_variant}")
    print("=" * 80)

    # Load data
    config.database.table = TAXONOMY_TABLES[taxonomy_level]
    df = load_and_prep_data()

    splitter = TrainTestSplit(
        df,
        n_splits=config.data_splitting.n_splits,
        test_size=config.data_splitting.test_size,
    )

    # Stage 1: Baseline models
    print("\nRunning STAGE 3.1: Baseline model ranking...")
    stage1_models = model_registry.get_baseline_models()

    run_name = f"stage3_baseline_{taxonomy_level}_{int(time.time())}"
    with start_run(run_name=run_name):
        mlflow.set_tag("stage", "stage3_full_pipeline")
        mlflow.set_tag("substage", "baseline")
        mlflow.set_tag("taxonomy_level", taxonomy_level)
        mlflow.set_tag("fe_variant", fe_variant)

        top_stage1, _ = _rank_models(splitter, stage1_models, use_network_features=False, top_k=3)

        for i, model_res in enumerate(top_stage1, 1):
            print(f"  {i}. {model_res['name']}: {model_res['avg_mekm']:.4f} km")

    best_model = top_stage1[0]
    print(f"\n✓ BEST BASELINE MODEL: {best_model['name']}")

    # Stage 2: With feature engineering (optional; commented in your original code)
    print("\nSTAGE 3.2: Re-evaluate with feature engineering...")
    run_name = f"stage3_fe_{taxonomy_level}_{int(time.time())}"
    with start_run(run_name=run_name):
        mlflow.set_tag("stage", "stage3_full_pipeline")
        mlflow.set_tag("substage", "feature_engineering")
        mlflow.set_tag("taxonomy_level", taxonomy_level)
        mlflow.set_tag("fe_variant", fe_variant)
        mlflow.set_tag("use_network_features", "True")

        # TODO: Uncomment and run if ready
        # top_stage2, _ = _rank_models(splitter, [best_model], use_network_features=True, top_k=1)

        print("  (Placeholder: re-evaluate top baseline models with feature engineering)")

    # Stage 3: Hyperparameter tuning
    print("\nSTAGE 3.3: Hyperparameter tuning (top model)...")
    if config.stage_3.enabled:
        run_name = f"stage3_tuning_{taxonomy_level}_{int(time.time())}"
        with start_run(run_name=run_name):
            mlflow.set_tag("stage", "stage3_full_pipeline")
            mlflow.set_tag("substage", "hyperparameter_tuning")
            mlflow.set_tag("taxonomy_level", taxonomy_level)
            mlflow.set_tag("fe_variant", fe_variant)

            # TODO: Uncomment and run if ready
            # best_tuned_model = _tune_top_model(splitter, best_model)
            # mlflow.sklearn.log_model(best_tuned_model, artifact_path="tuned_model")

            print("  (Placeholder: hyperparameter tuning to be enabled)")
    else:
        print("  (Stage 3 disabled in config; skipping hyperparameter tuning)")

    print("\n" + "-" * 80)
    print("✓ STAGE 3 COMPLETE")
    print("-" * 80)


# ============================================================================
# Main orchestration
# ============================================================================
def main():
    """
    Orchestrate all three experiment stages.
    """

    # Set global MLflow experiment
    mlflow.set_experiment(config.mlflow.experiment_name)

    try:
        # Stage 1: Determine best taxonomy level
        best_taxonomy, stage1_results = run_stage2_taxonomy_baseline()

        # Stage 2: Determine best feature engineering approach
        #best_fe, stage2_results = run_stage2_feature_engineering("genus")

        # Stage 3 remains optional/disabled unless you explicitly enable it later
        # run_stage3_final_tuning(best_taxonomy, best_fe)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
