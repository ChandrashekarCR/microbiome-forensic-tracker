from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from xgboost import XGBRegressor

from ml.config import config


class ModelRegistry:
    """
    Dynamically loads model definitions from config.yaml
    """

    # Master map linking strings in configuration to real Python classes
    MODEL_MAPPING = {
        "XGBoost": XGBRegressor,
        "RandomForest": RandomForestRegressor,
        "RidgeRegression": Ridge,
        "NeuralNetwork": MLPRegressor,
    }

    @staticmethod
    def _instantiate_model(model_class, params: dict):
        """
        Helper to create a model instance from class + params dict
        """
        # Filter out None values and invalid params
        # Parameters is set to None if mentioned in the config file
        filtered_params = {k: v for k, v in params.items() if v is not None}
        return model_class(**filtered_params)

    @staticmethod
    def get_baseline_models(allowed_families: list = None):
        """
        Stage 1: Load all baseline models from config.yaml
        Returns list of dicts with {name, estimator, params}
        """
        stage_1_config = config.stage_1  # This is from the config file
        active_models = []

        for model_name, model_meta in stage_1_config.items():
            # 1. Skip models that have enabled set to False
            if not model_meta.get("enabled", True):
                continue

            # 2. Track model family (tree, linear, nn)
            family = model_meta.get("family", "unknown")

            # 3. Optional filter: skip if we specified families and this doesn't match
            if allowed_families and family not in allowed_families:
                continue

            model_class = ModelRegistry.MODEL_MAPPING.get(model_name)
            if model_class is None:
                print(f"Warning: Model {model_name} missing from MODEL_MAPPING dictionary.")
                continue

            # Extract inner parameters block
            params = model_meta.get("params", {})
            estimator = ModelRegistry._instantiate_model(model_class, params)

            active_models.append({"name": f"{model_name}_baseline", "estimator": estimator, "family": family, "model_type": model_name})

        return active_models


models = ModelRegistry()

if __name__ == "__main__":
    # Example 1: Pull ALL enabled baseline models
    print("--- All Enabled Baselines ---")
    for m in models.get_baseline_models():
        print(f"Loaded {m['name']} belonging to family: {m['family']}")

    # Example 2: Pull ONLY linear models for a quick experiment
    print("\n--- Only Linear Models ---")
    for m in models.get_baseline_models(allowed_families=["linear"]):
        print(f"Loaded {m['name']}")
