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
from ml.pipeline import evaluate_model_cv, get_configured_cv_split, build_pipeline
import time
import json
from omegaconf import ListConfig
from sklearn.base import clone
from sklearn.model_selection import RandomizedSearchCV
import mlflow

TAXONOMY_TABLES = {
    "phylum": "malmo_phylum",
    "class": "malmo_class",
    "order": "malmo_order",
    "family": "malmo_family",
    "genus": "malmo_genus",
    "species": "malmo_species",
}


# STAGE 1: Taxonomy Baseline
# In this stage, we are intrested in which of the following models from our config file and
# which of the following taxonomy levels give the best result, i.e least mean_error_km

def run_stage1_taxonomy_baseline(model_type: str = "ExtraTreesRegressor"):
    """
    Experiment 1: Determine which taxonomy level provides best geolocation signal.
    Uses all baseline models (no feature engineering, no hyperparameter tuning).
    """
    print(f"STAGE 1: Taxonomy Baseline {model_type} (no feature engineering, no hyperparameter tuning)")

    stage1_results = {}

    # Get the baseline models from the model registry
    all_models = []
    for m in model_registry.get_baseline_models():
        all_models.append(m)

    if model_type:
        selected_model = next((m for m in all_models if m["model_type"] == model_type), None)
        if selected_model is None:
            available = [m["model_type"] for m in all_models]
            raise ValueError(f"Model '{model_type}' not enabled. Available: {available}")
    else:
        selected_model = all_models[0]  # Use first enabled model
        model_type = selected_model["model_type"]

    model_family = selected_model["family"]  # tree or linear

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
            mlflow.log_params(
                {
                    "taxonomy_table": table,
                    "model_type": model_type,
                    "model_family": model_family,
                    "n_samples": len(df),
                    "cv_strategy": config.pipeline_excecution.get("cv_strategy"),
                    "use_meters": config.pipeline_excecution.get("use_cartesian_meters"),
                }
            )

            # Log XGBoost model hyperparameters
            log_model_params(selected_model["estimator"])

            # Evaluate the model across CV folds
            print(f"Evaluating {selected_model['model_type']} with {config.data_splitting.n_splits} splits...")
            avg_mekm, summary_metrics = evaluate_model_cv(
                splitter, selected_model["estimator"], use_network_features=False, use_k_best=False, feature_flags=None, model_family=model_family
            )

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


# STAGE 2: Feature Engineering Variants - Use K-best features

def run_stage2_fe_kbest(taxonomy_level: str, model_type: str = "RandomForest"):
    """
    Experiment 2: Given the best taxonomy level, test feature engineering variants.
    Tests network feature combinations + RFE on/off.
    """
    print(f"STAGE 2: Feature Engineering - Use K-best features taxonomy: {taxonomy_level}, no hyperparameter tuning, model: {model_type}")

    # Get the baseline models from the model registry
    all_models = []
    for m in model_registry.get_baseline_models():
        all_models.append(m)

    if model_type:
        selected_model = next((m for m in all_models if m["model_type"] == model_type), None)
        if selected_model is None:
            available = [m["model_type"] for m in all_models]
            raise ValueError(f"Model '{model_type}' not enabled. Available: {available}")
    else:
        selected_model = all_models[0]  # Use first enabled model
        model_type = selected_model["model_type"]

    model_family = selected_model["family"]  # tree or linear

    print(f"Using model:{model_type}, family: {model_family}")

    # Load data for best taxonomy level
    config.database.table = TAXONOMY_TABLES[taxonomy_level]
    df = load_and_prep_data()

    splitter = TrainTestSplit(
        df,
        n_splits=config.data_splitting.n_splits,
        test_size=config.data_splitting.test_size,
    )

    stage2_results = {}

    run_name = f"stage2_fe_kbest_{model_type}_{int(time.time())}"

    with start_run(run_name=run_name):
        # === TAGS ===
        mlflow.set_tag("stage", "stage2_fe_kbest")
        mlflow.set_tag("taxonomy_level", taxonomy_level)
        mlflow.set_tag("model_type", model_type)
        mlflow.set_tag("use_k_best", "True")

        # === PARAMETERS ===
        mlflow.log_params(
            {
                "model_type": model_type,
                "taxonomy_level": taxonomy_level,
                "n_samples": len(df),
                "cv_strategy": config.pipeline_excecution.get("cv_strategy"),
                "use_meters": config.pipeline_excecution.get("use_cartesian_meters"),
            }
        )
        # Log XGBoost parameters
        log_model_params(selected_model["estimator"])

        # === EVALUATE ===
        avg_mekm, summary_metrics = evaluate_model_cv(
            splitter=splitter,
            estimator=selected_model["estimator"],
            use_network_features=False,
            use_k_best=True,
            feature_flags=None,
            model_family=model_family,
        )

        # Log metrics
        log_model_metrics(metrics=summary_metrics)

        # Store result
        stage2_results["kbest"] = {"avg_mekm": avg_mekm, "run_id": mlflow.active_run().info.run_id, "metrics": summary_metrics}
        print(f"Mean error: {avg_mekm:.4f} km")

    return stage2_results

# STAGE 3: Feature Engineering without kbest
def run_stage3_fe_network(taxonomy_level: str, model_type: str = "RandomForest", use_kbest: bool = False):
    """
    Experiment 3: Given the best taxonomy level, best model, best k features, test feature engineering.
    Evaluate the best network features.
    """
    print(f"STAGE 3: Feature Engineering - Network Features taxonomy: {taxonomy_level}, no hyperparameter tuning, model: {model_type}")

    # Get the baseline models from the model registry
    all_models = []
    for m in model_registry.get_baseline_models():
        all_models.append(m)

    if model_type:
        selected_model = next((m for m in all_models if m["model_type"] == model_type), None)
        if selected_model is None:
            available = [m["model_type"] for m in all_models]
            raise ValueError(f"Model '{model_type}' not enabled. Available: {available}")
    else:
        selected_model = all_models[0]  # Use first enabled model
        model_type = selected_model["model_type"]

    model_family = selected_model["family"]  # tree or linear

    print(f"Using model:{model_type}, family: {model_family}")

    # Load data for best taxonomy level
    config.database.table = TAXONOMY_TABLES[taxonomy_level]
    df = load_and_prep_data()

    splitter = TrainTestSplit(
        df,
        n_splits=config.data_splitting.n_splits,
        test_size=config.data_splitting.test_size,
    )

    stage3_results = {}

    # Generate ALL combinations of feature flags
    # This creates 16 combinations (2^4)
    feature_combinations = [
        # (use_clr, use_degree, use_hub, use_edge)
        (True, False, False, False),  # CLR only
        (False, True, False, False),  # Degree only
        (False, False, True, False),  # Hub only
        (False, False, False, True),  # Edge only
        (True, True, False, False),  # CLR + Degree
        (True, False, True, False),  # CLR + Hub
        (True, False, False, True),  # CLR + Edge
        (False, True, True, False),  # Degree + Hub
        (False, True, False, True),  # Degree + Edge
        (False, False, True, True),  # Hub + Edge
        (True, True, True, False),  # CLR + Degree + Hub
        (True, True, False, True),  # CLR + Degree + Edge
        (True, False, True, True),  # CLR + Hub + Edge
        (False, True, True, True),  # Degree + Hub + Edge
        (True, True, True, True),  # ALL features
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

        print(f"Variant: {fe_name}")
        print(f"Flags: CLR={use_clr}, Deg={use_degree}, Hub={use_hub}, Edge={use_edge}")

        run_name = f"stage3_fe_{model_type}_{fe_name}_{int(time.time())}"

        with start_run(run_name=run_name):
            # === TAGS ===
            mlflow.set_tag("stage", "stage3_fe_network")
            mlflow.set_tag("taxonomy_level", taxonomy_level)
            mlflow.set_tag("fe_variant", fe_name)
            mlflow.set_tag("model_type", model_type)
            mlflow.set_tag("use_kbest",use_kbest)

            # === FEATURE FLAG TAGS ===
            mlflow.set_tag("use_clr", str(use_clr))
            mlflow.set_tag("use_degree", str(use_degree))
            mlflow.set_tag("use_hub", str(use_hub))
            mlflow.set_tag("use_edge", str(use_edge))

            # === PARAMETERS ===
            mlflow.log_params(
                {
                    "top_k_edges": config.feature_engineering.top_k_edges,
                    "cv_strategy": config.pipeline_excecution.get("cv_strategy"),
                    "use_meters": config.pipeline_excecution.get("use_cartesian_meters"),
                }
            )

            # Log XGBoost parameters
            log_model_params(selected_model["estimator"])

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
                estimator=selected_model["estimator"],
                use_network_features=True,
                use_k_best=use_kbest,
                feature_flags=feature_config,
            )

            # Log metrics
            log_model_metrics(metrics=summary_metrics)

            # Store result
            stage3_results[fe_name] = {
                "fe_type": "feature_combination",
                "fe_variant": fe_name,
                "use_clr": use_clr,
                "use_degree": use_degree,
                "use_hub": use_hub,
                "use_edge": use_edge,
                "avg_mekm": avg_mekm,
                "run_id": mlflow.active_run().info.run_id,
            }

            print(f"Mean error: {avg_mekm:.4f} km")

    sorted_results = sorted(stage3_results.items(), key=lambda x: x[1]["avg_mekm"])

    # Find best variant
    best_variant = sorted_results[0][0]
    best_error = sorted_results[0][1]["avg_mekm"]

    print(f"Best Feature Engineering: {best_variant}")
    print(f"Mean error: {best_error:.4f} km")

    return best_variant, stage3_results


# Stage 4: Full Pipeline Hyperparameter Tuning

def run_stage4_hyperparameter_tuning(
    taxonomy_level: str,
    model_type: str = "RandomForest",
    use_network_features: bool = False,
    use_kbest: bool = True,
    feature_flags: dict = None,
    n_iter: int = 20,
):
    """
    Stage 4: Hyperparameter tuning with MLflow logging.

    Reuses existing functions: build_pipeline, evaluate_model_cv, get_configured_cv_split.
    Logs search results, best parameters, and final model to MLflow.

    Returns
    -------
    final_pipeline : Pipeline
        Fitted on the full training set.
    best_error_km : float
        Cross‑validated mean error in km (evaluated via evaluate_model_cv).
    best_params : dict
        Cleaned best hyperparameters.
    run_id : str
        MLflow run ID.
    """
    
    # Load the data from the database
    config.database.table = TAXONOMY_TABLES[taxonomy_level]
    df = load_and_prep_data()

    # Split the data same as before
    splitter = TrainTestSplit(
        df,
        n_splits=config.data_splitting.n_splits,
        test_size=config.data_splitting.test_size,
    )

    # 2. Get base model and family
    all_models = model_registry.get_baseline_models()
    selected_model = next((m for m in all_models if m["model_type"] == model_type), None)
    if selected_model is None:
        raise ValueError(f"Model '{model_type}' not found in registry.")
    model_family = selected_model["family"]
    base_estimator = selected_model["estimator"]

    # 3. Prepare hyperparameter grid
    if model_type not in config.stage_3.grids:
        raise ValueError(f"No hyperparameter grid for {model_type} in config.stage_3.grids")
    param_grid = config.stage_3.grids[model_type]
    param_distributions = {}
    for param, values in param_grid.items():
        if isinstance(values, ListConfig):
            values = list(values)
        param_distributions[f"model__estimator__{param}"] = values

    # 4. Get CV splits (same strategy as evaluate_model_cv)
    cv_splits = get_configured_cv_split(splitter)

    # 5. Prepare target columns
    use_meters = config.pipeline_excecution.get("use_cartesian_meters", True)
    y_cols = ["X_meters", "Y_meters"] if use_meters else ["latitude", "longitude"]
    X_cv = splitter.X_cv
    y_cv = splitter.y_cv_coords[y_cols]

    # 6. Start MLflow run
    run_name = f"stage4_tuning_{model_type}_{taxonomy_level}_{int(time.time())}"
    with start_run(run_name=run_name):
        # Tags
        mlflow.set_tag("stage", "stage4_hyperparameter_tuning")
        mlflow.set_tag("taxonomy_level", taxonomy_level)
        mlflow.set_tag("model_type", model_type)
        mlflow.set_tag("use_network_features", str(use_network_features))
        mlflow.set_tag("use_kbest", str(use_kbest))

        # Log fixed parameters
        mlflow.log_params({
            "n_iter": n_iter,
            "cv_strategy": config.pipeline_excecution.get("cv_strategy"),
            "use_meters": use_meters,
            "k_best_features": config.feature_engineering.k_best_features,
            "top_k_edges": config.feature_engineering.top_k_edges,
        })
        if feature_flags:
            mlflow.log_params({f"fe_{k}": v for k, v in feature_flags.items()})

        # 7. Build pipeline (once, for the search)
        pipeline = build_pipeline(
            estimator=clone(base_estimator),
            use_network_features=use_network_features,
            use_k_best=use_kbest,
            feature_flags=feature_flags,
            model_family=model_family,
        )

        # 8. Run RandomizedSearchCV
        print(f"\nTuning {model_type} on {taxonomy_level} with {n_iter} iterations...")
        search = RandomizedSearchCV(
            estimator=pipeline,
            param_distributions=param_distributions,
            n_iter=n_iter,
            cv=cv_splits,
            scoring="neg_mean_squared_error",
            random_state=config.stage_3.random_state,
            n_jobs=8,
            verbose=1,

        )
        search.fit(X_cv, y_cv)

        # 9. Log each iteration score with a distinct step
        cv_results = search.cv_results_
        for i, params in enumerate(cv_results["params"]):
            score = cv_results["mean_test_score"][i]
            # Skip NaN scores (they will be logged as NaN anyway)
            mlflow.log_metric(f"search_iter_{i}_neg_mse", score, step=i)

        # 10. Log best parameters
        best_params_raw = search.best_params_
        best_params_clean = {
            k.replace("model__estimator__", ""): v for k, v in best_params_raw.items()
        }
        mlflow.log_params({f"tuned_{k}": v for k, v in best_params_clean.items()})
        mlflow.log_metric("search_best_neg_mse", search.best_score_, step=n_iter)  # use a unique step
        
        # 11. Re‑evaluate the tuned model using your kilometer metrics (full CV)
        print("\nRe‑evaluating tuned model with kilometer metrics...")
        tuned_estimator = clone(base_estimator)
        tuned_estimator.set_params(**best_params_clean)

        avg_error_km, summary_metrics = evaluate_model_cv(
            splitter=splitter,
            estimator=tuned_estimator,
            use_network_features=use_network_features,
            use_k_best=use_kbest,
            feature_flags=feature_flags,
            model_family=model_family,
        )
        # Log the km metrics
        log_model_metrics(metrics=summary_metrics)
        print(f"Tuned model CV mean error: {avg_error_km:.4f} km")

        # 12. Fit final pipeline on the full training set
        print("\nFitting final pipeline on full training set...")
        final_pipeline = build_pipeline(
            estimator=clone(tuned_estimator),
            use_network_features=use_network_features,
            use_k_best=use_kbest,
            feature_flags=feature_flags,
            model_family=model_family,
        )
        final_pipeline.fit(X_cv, y_cv)

        # 13. Log the model artifact
        mlflow.sklearn.log_model(final_pipeline, name="final_tuned_model")

        # 14. Save minimal metadata (optional)
        metadata = {
            "taxonomy_level": taxonomy_level,
            "model_type": model_type,
            "use_network_features": use_network_features,
            "use_kbest": use_kbest,
            "feature_flags": feature_flags,
            "best_params": best_params_clean,
            "cv_mean_error_km": avg_error_km,
            "use_meters": use_meters,
            "run_id": mlflow.active_run().info.run_id,
        }
        with open("final_model_metadata.json", "w") as f:
            json.dump(metadata, f, indent=2, default=str)
        mlflow.log_artifact("final_model_metadata.json")

        print(f"\nStage 4 complete. Run ID: {mlflow.active_run().info.run_id}")
        return final_pipeline, avg_error_km, best_params_clean, mlflow.active_run().info.run_id



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
        # best_taxonomy, stage1_results = run_stage1_taxonomy_baseline(model_type="ExtraTreesRegressor")

        # Stage 2: Determine best feature engineering approach
        #stage2_results = run_stage2_fe_kbest("species", "RandomForest")

        # Stage 3: Determine the best combination of network features
        #best_variant, stage3_results = run_stage3_fe_network("phylum", "RandomForest",use_kbest=False)

        # Stage 4 remains optional/disabled unless you explicitly enable it later
        # Tune RandomForest on genus level without network features
        best_pipe, error, params, run_id = run_stage4_hyperparameter_tuning(
            taxonomy_level="species",
            model_type="RandomForest",
            use_network_features=False,
            use_kbest=True,
            n_iter=60
        )

        print(f"Best error: {error:.2f} km")
        print(f"Best params: {params}")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
