"""
This is like a wrapper fucntion that will run to read the abundance information from the database.
Then it will load the model from the trained model.
Then it will run the model and then predict the latitude and longitude.
"""

from pathlib import Path
from pyproj import Transformer


import pandas as pd
import joblib


from .config import Settings

# Valid taxonomy ranks — must match what's stored in your DB
VALID_RANKS = {"phylum", "class", "order", "family", "genus", "species"}
settings = Settings()

def get_pipeline():
    """
    Load the trained sklearn model for a given taxonomy rank.

    Expected file layout (set MODEL_DIR in .env):
        models/
            genus_model.pkl
            species_model.pkl
            phylum_model.pkl
            ...

    Each .pkl must contain a fitted sklearn model with:
        - model.predict(X) → array of shape (1, 2) = [[lat, lon]]
        - model.feature_names_in_ → list of clade names it was trained on
    """
    model_path = Path(settings.MODEL_PATH)

    if not model_path.exists():
        raise FileNotFoundError(
            f"No model found at {model_path}. "
        )

    with open(model_path, "rb") as f:
        pipeline = joblib.load(f)

    return pipeline



def predict_sample(wide_df: pd.DataFrame) -> tuple[float,float]:
    """
    Takes a wide_df as input after access the database through crud.py
    Predicts the latitude and longitude.    
    """

    # Get the pipline
    pipeline = get_pipeline()

    # Get the exact feature columns in the pipeline
    FEATURE_COLUMNS = pipeline.named_steps["zeros_filter"]._keep_cols_

    # Align incoming data to expected columns, fill missing with 0
    row = {col: float(wide_df[col].iloc[0]) if col in wide_df.columns else 0.0
           for col in FEATURE_COLUMNS}
    X = pd.DataFrame([row], columns=FEATURE_COLUMNS)

    # Predict → [X_meters, Y_meters] in EPSG:3006
    pred = pipeline.predict(X)
    x_meters, y_meters = pred[0]

    # Convert to lat/lon
    transformer = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x_meters, y_meters)

    return lat, lon