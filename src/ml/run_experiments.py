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
import numpy as np
from omegaconf import OmegaConf

from ml.config import config
from ml.mlflow_utils import start_run, log_model_metrics, log_model_params
from ml.models import load_and_prep_data, TrainTestSplit
from ml.model_registry import models as model_registry
from ml.pipeline import build_pipeline, evaluate_model_cv, _rank_models, _tune_top_model
from ml.features import ZeroColumnFilter


TAXONOMY_TABLES = {
    "phylum": "malmo_phylum",
    "class": "malmo_class",
    "order": "malmo_order",
    "family": "malmo_family",
    "genus": "malmo_genus",
    "species": "malmo_species"
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


# ============================================================================
# STAGE 1: Taxonomy Baseline
# ============================================================================
def run_stage1_taxonomy_baseline():
    """
    Experiment 1: Determine which taxonomy level provides best geolocation signal.
    Uses ONLY XGBoost baseline (no feature engineering, no hyperparameter tuning).
    """
    print("STAGE 1: Taxonomy Baseline (XGBoost only, no feature engineering, no hyperparameter tuning)")
    
    stage1_results = {}
    
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
        
        # Get the XGBoost baseline model
        xgb_models = [m for m in model_registry.get_baseline_models() if m['model_type'] == "XGBoost"]
        if not xgb_models:
            print(f"WARNING: XGBoost not found in baseline models. Skipping {level}.")
            continue
        
        xgb_def = xgb_models[0]
        
        # Create MLflow run
        run_name = f"stage1_baseline_{level}_{int(time.time())}"
        with start_run(run_name=run_name):
            # Set experiment tags
            mlflow.set_tag("stage", "stage1_taxonomy_baseline")
            mlflow.set_tag("taxonomy_level", level)
            mlflow.set_tag("model_type", "XGBoost")
            mlflow.set_tag("use_network_features", "False")
            
            # Log config parameters (compact; avoid huge dict)
            mlflow.log_param("taxonomy_table", table)
            mlflow.log_param("n_samples", len(df))
            mlflow.log_param("n_taxa_features", df.shape[1] - 3)  # exclude metadata
            mlflow.log_param("cv_strategy", config.pipeline_excecution.get("cv_strategy"))
            mlflow.log_param("use_meters", config.pipeline_excecution.get("use_cartesian_meters"))
            
            # Log XGBoost model hyperparameters
            log_model_params(xgb_def['estimator'])
            
            # Evaluate the model across CV folds
            print(f"Evaluating {xgb_def['name']} with {config.data_splitting.n_splits} splits...")
            avg_mekm, summary_metrics = evaluate_model_cv(
                splitter, 
                xgb_def["estimator"], 
                use_network_features=False
            )
            
            # Log evaluation metrics
            log_model_metrics(metrics=summary_metrics)
            
            # Store result
            stage1_results[level] = {
                "model_name": xgb_def['name'],
                "avg_mekm": avg_mekm,
                "metrics": summary_metrics,
                "run_id": mlflow.active_run().info.run_id
            }
            
            print(f"Mean error: {avg_mekm:.4f} km")
    
    # Print summary
    print("Experiment 1 Summary:")
    sorted_results = sorted(stage1_results.items(), key=lambda x: x[1]['avg_mekm'])
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
    
    stage2_results = {}
    
    # Test 1: Network feature variants
    print("\nTesting Network Feature Variants...")
    xgb_models = [m for m in model_registry.get_baseline_models() if m['model_type'] == "XGBoost"]
    xgb_def = xgb_models[0]
    
    for fe_name, use_clr, use_degree, use_hub in FE_VARIANTS:
        print(f"\n  >>> Variant: {fe_name}")
        
        run_name = f"stage2_network_{fe_name}_{taxonomy_level}_{int(time.time())}"
        with start_run(run_name=run_name):
            mlflow.set_tag("stage", "stage2_feature_engineering")
            mlflow.set_tag("taxonomy_level", taxonomy_level)
            mlflow.set_tag("fe_variant", fe_name)
            mlflow.set_tag("fe_type", "network_features")
            mlflow.set_tag("use_clr", str(use_clr))
            mlflow.set_tag("use_degree", str(use_degree))
            mlflow.set_tag("use_hub", str(use_hub))
            mlflow.set_tag("use_rfe", "False")
            
            mlflow.log_param("fe_variant", fe_name)
            mlflow.log_param("model_type", "XGBoost")
            
            # TODO: For now, we log the intent. In a later iteration, you would extend
            # MicrobiomeFeatureEngineer to accept feature_subset parameters.
            # For this demo, we evaluate with use_network_features=True (all features enabled).
            
            print(f"(Future: would use_clr={use_clr}, use_degree={use_degree}, use_hub={use_hub})")
            
            # Evaluate with network features enabled (full set)
            avg_mekm, summary_metrics = evaluate_model_cv(
                splitter,
                xgb_def["estimator"],
                use_network_features=True
            )
            
            log_model_metrics(metrics=summary_metrics)
            
            stage2_results[f"network_{fe_name}"] = {
                "fe_type": "network_features",
                "fe_variant": fe_name,
                "avg_mekm": avg_mekm,
                "run_id": mlflow.active_run().info.run_id
            }
            
            print(f"Mean error: {avg_mekm:.4f} km")
    
    # Test 2: RFE variant (sketch; full RFE implementation would go here)
#    print("\n  Testing RFE (Recursive Feature Elimination)...")
#    run_name = f"stage2_rfe_{taxonomy_level}_{int(time.time())}"
#    with start_run(run_name=run_name):
#        mlflow.set_tag("stage", "stage2_feature_engineering")
#        mlflow.set_tag("taxonomy_level", taxonomy_level)
#        mlflow.set_tag("fe_type", "rfe")
#        mlflow.set_tag("use_rfe", "True")
#        
#        mlflow.log_param("model_type", "XGBoost")
#        mlflow.log_param("fe_type", "rfe")
#        
#        # TODO: Wrap RFE logic here when ready (see RecursiveFeatureElimination class in features.py)
#        print("      (Placeholder: RFE implementation to be added)")
#        
#        avg_mekm, summary_metrics = evaluate_model_cv(
#            splitter,
#            xgb_def["estimator"],
#            use_network_features=False  # RFE replaces network features
#        )
#        
#        log_model_metrics(metrics=summary_metrics)
#        
#        stage2_results["rfe"] = {
#            "fe_type": "rfe",
#            "fe_variant": "rfe",
#            "avg_mekm": avg_mekm,
#            "run_id": mlflow.active_run().info.run_id
#        }
#        
#        print(f"Mean error: {avg_mekm:.4f} km")
#    
#    # Test 3: Network + RFE combo
#    print("\n  Testing NETWORK + RFE (combined)...")
#    run_name = f"stage2_network_rfe_{taxonomy_level}_{int(time.time())}"
#    with start_run(run_name=run_name):
#        mlflow.set_tag("stage", "stage2_feature_engineering")
#        mlflow.set_tag("taxonomy_level", taxonomy_level)
#        mlflow.set_tag("fe_type", "network_rfe")
#        mlflow.set_tag("use_network_features", "True")
#        mlflow.set_tag("use_rfe", "True")
#        
#        mlflow.log_param("model_type", "XGBoost")
#        mlflow.log_param("fe_type", "network_rfe")
#        
#        print("      (Placeholder: combined network + RFE to be added)")
#        
#        avg_mekm, summary_metrics = evaluate_model_cv(
#            splitter,
#            xgb_def["estimator"],
#            use_network_features=True  # Both enabled
#        )
#        
#        log_model_metrics(metrics=summary_metrics)
#        
#        stage2_results["network_rfe"] = {
#            "fe_type": "network_rfe",
#            "fe_variant": "network_rfe",
#            "avg_mekm": avg_mekm,
#            "run_id": mlflow.active_run().info.run_id
#        }
#        
#        print(f"      Mean error: {avg_mekm:.4f} km")
    
    # Print summary
    print("Stage 2 Summary:")
    sorted_results = sorted(stage2_results.items(), key=lambda x: x[1]['avg_mekm'])
    for i, (variant, res) in enumerate(sorted_results, 1):
        print(f"{i}. {variant:25} → {res['avg_mekm']:8.4f} km")
    
    best_fe = sorted_results[0]
    print(f"\n✓ BEST FEATURE ENGINEERING: {best_fe[0]}")
    print("-"*80)
    
    return best_fe[0], stage2_results


# ============================================================================
# STAGE 3: Full Multistage Pipeline + Hyperparameter Tuning
# ============================================================================
def run_stage3_final_tuning(taxonomy_level: str, fe_variant: str):
    """
    Experiment 3: Full pipeline with all models + feature engineering + hyperparameter tuning.
    Selects and saves the best model.
    """
    print("\n" + "="*80)
    print(f"STAGE 3: FULL MULTISTAGE PIPELINE + HYPERPARAMETER TUNING")
    print(f"         Taxonomy: {taxonomy_level}, FE: {fe_variant}")
    print("="*80)
    
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
    
    print("\n" + "-"*80)
    print("✓ STAGE 3 COMPLETE")
    print("-"*80)


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
        best_taxonomy, stage1_results = run_stage1_taxonomy_baseline()
        
        # Stage 2: Determine best feature engineering approach
        #best_fe, stage2_results = run_stage2_feature_engineering(best_taxonomy)
        #
        ## Stage 3: Full pipeline with hyperparameter tuning
        #run_stage3_final_tuning(best_taxonomy, best_fe)
        
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()