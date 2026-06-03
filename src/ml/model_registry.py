from lightgbm import LGBMRegressor
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor

from ml.config import config


class ModelRegistry:
    """
    Dynamically loads model definitions from config.yaml
    """

    @staticmethod
    def _instantiate_model(model_class, params: dict):
        """
        Helper to create a model instance from class + params dict
        """
        # Filter out None values and invalid params
        filtered_params = {k: v for k, v in params.items() if v is not None}
        return model_class(**filtered_params)

    @staticmethod
    def get_baseline_models():
        """
        Stage 1: Load all baseline models from config.yaml
        Returns list of dicts with {name, estimator, params}
        """
        stage_1_config = config.stage_1
        models = []

        model_classes = {"XGBoost": XGBRegressor, "RandomForest": RandomForestRegressor}

        for model_name, params in stage_1_config.items():
            model_class = model_classes.get(model_name)
            if model_class is None:
                print(f"Warning: Model {model_name} not found in registry")
                continue

            estimator = ModelRegistry._instantiate_model(model_class, params)

            models.append({"name": f"{model_name}_baseline", "estimator": estimator, "params": params, "model_type": model_name})

        return models


models = ModelRegistry()

if __name__ == "__main__":
    print(models.get_baseline_models())
