# Importing libraries
import time
from typing import Dict, Optional

import mlflow
import mlflow.sklearn

from ml.config import config


# Get the experiment name
def get_experiment_id() -> str:
    """
    Get or create the MLflow experiment and return its IDs.
    This will just return 1,2,3...
    """

    experiment_name = config.mlflow.experiment_name
    # Pass the experiment name to mlflow tracking
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        experiment_id = mlflow.create_experiment(experiment_name)
    else:
        experiment_id = experiment.experiment_id

    return experiment_id


# Start the MLflow run
def start_run(run_name: Optional[str] = None, nested: bool = False):
    """
    Start and MLflow run with automatic experiment setup.

    Usage:
        with start_run(run_name="baseline_xgboost") as run:
            # The code for running the model

    """
    experiment_id = get_experiment_id()

    # Generate default run if not provied
    if run_name is None:
        run_name = f"{config.mlflow.run_name_prefix}_{int(time.time())}"

    return mlflow.start_run(experiment_id=experiment_id, run_name=run_name, nested=nested)


def log_model_params(model):
    """
    Log model parameters
    """
    if hasattr(model, "get_params"):
        params = model.get_params()
        mlflow.log_params({f"model_{k}": v for k, v in params.items()})


def log_model_metrics(metrics: Dict[str, float], step: Optional[int] = None):
    """
    Log evaluation metrics. A custom evalution metrics is set to measeure the cartesion and haversine distance
    """
    for key, value in metrics.items():
        mlflow.log_metric(key, value, step=step)


def log_feature_count(metric_name: str, count: int, fold: int = None):
    """
    Log a feature-count metric to MLflow if a run is active.
    The idea behind this is after every feature engineering step there are features which are removed.
    We need to keep track of how many features are remaining after filtering.
    """
    if fold is None:
        mlflow.log_metric(metric_name, float(count))
    else:
        mlflow.log_metric(metric_name, float(count), step=fold)
