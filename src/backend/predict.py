"""
This is like a wrapper fucntion that will run to read the abundance information from the database.
Then it will load the model from the trained model.
Then it will run the model and then predict the latitude and longitude.
"""

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import Abundance

# Valid taxonomy ranks — must match what's stored in your DB
VALID_RANKS = {"phylum", "class", "order", "family", "genus", "species"}
settings = Settings()

def load_model():
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
    print(model_path)

    if not model_path.exists():
        raise FileNotFoundError(
            f"No model found at {model_path}. "
        )

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    return model


load_model()