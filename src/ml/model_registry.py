from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, Ridge
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
        "ElasticNet": ElasticNet,
        "ExtraTreesRegressor": ExtraTreesRegressor,
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
    # Test 1: Load all enabled models
    print("All enabled models:")
    for m in models.get_baseline_models():
        print(f"  {m['name']} (family: {m['family']})")

    # Test 2: Load specific family
    print("\nOnly tree models:")
    for m in models.get_baseline_models(allowed_families=["tree"]):
        print(f"  {m['name']}")

    # Test 3: Instantiate a model and check it works
    # from sklearn.datasets import make_regression
#
# X, y = make_regression(n_samples=100, n_features=5, noise=0.1)
# models_list = models.get_baseline_models()
#
# for m in models_list:
#    try:
#        estimator = m['estimator']
#        estimator.fit(X, y)
#        pred = estimator.predict(X[:5])
#        print(f"{m['model_type']} works! Prediction: {pred[:2]}")
#    except Exception as e:
#        print(f"{m['model_type']} failed: {e}")
