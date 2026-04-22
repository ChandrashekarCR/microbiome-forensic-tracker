import pandas as pd
import numpy as np
from sklearn.model_selection import StratifiedKFold, train_test_split
from xgboost import XGBRegressor, XGBClassifier
from sklearn.base import BaseEstimator, TransformerMixin

from ml.data_loading import DatabaseRSA
from malmo_samples import db_reader

from ml.config import config

# Load the data from the SQL database
def load_and_prep_data() -> pd.DataFrame:
    """ Load from SQLite, merge metadata, drop NaNs. """
    samples = db_reader.DatabaseCreate(db=config.database.path)
    rsa = DatabaseRSA(db=config.database.path, db_table=config.database.table)
    df = rsa.merge_data(samples.get_samples(), rsa.sql_to_clean())
       
    return df

print(load_and_prep_data().head())

# Stratifier train test and validation
class TrainTestSplit:
    def __init__(self, df: pd.DataFrame, n_splits: int=4, test_size: float=0.2):
        X_all = df.drop(columns=["sample_id", "latitude", "longitude", "zone"], axis=1)
        y_zone_all = df['zone']
        y_coords_all = df[['latitude', 'longitude']]
        
        self.n_splits = n_splits
        
        # 1. Slice off the 20% blind test set first. Stratify by zone.
        (self.X_cv, self.X_test, 
         self.y_cv_zone, self.y_test_zone, 
         self.y_cv_coords, self.y_test_coords) = train_test_split(
            X_all, y_zone_all, y_coords_all, 
            test_size=test_size, 
            stratify=y_zone_all, 
            random_state=config.data_splitting.random_state
        )
        
        # Reset indices so K-Fold integer indexing (.iloc) works perfectly
        self.X_cv = self.X_cv.reset_index(drop=True)
        self.X_test = self.X_test.reset_index(drop=True)
        self.y_cv_zone = self.y_cv_zone.reset_index(drop=True)
        self.y_test_zone = self.y_test_zone.reset_index(drop=True)
        self.y_cv_coords = self.y_cv_coords.reset_index(drop=True)
        self.y_test_coords = self.y_test_coords.reset_index(drop=True)
    
    def stratifed_zone_data_split(self) -> list:
        """
        Returns K-fold indices for stratified CV on zone on the remaining 80% data
        """
        skf = StratifiedKFold(n_splits=self.n_splits, shuffle=True, random_state=config.data_splitting.random_state)
        return list(skf.split(self.X_cv, self.y_cv_zone))
    
    def get_fold_data(self, train_idx: int, val_idx: int) -> tuple:
        """
        Get X,y for a specific fold (60% Train, 20% Val)
        """
        X_train, X_val = self.X_cv.iloc[train_idx], self.X_cv.iloc[val_idx]
        y_train_zone, y_val_zone = self.y_cv_zone.iloc[train_idx], self.y_cv_zone.iloc[val_idx]
        y_train_coords, y_val_coords = self.y_cv_coords.iloc[train_idx], self.y_cv_coords.iloc[val_idx]

        return X_train, X_val, y_train_zone, y_val_zone, y_train_coords, y_val_coords

    def get_test_data(self) -> tuple:
        """
        Returns the pure 20% blind hold-out set untouched by CV.
        """
        return self.X_test, self.y_test_zone, self.y_test_coords

class XGBoostCoordinateModel(BaseEstimator,TransformerMixin):
    def __init__(self):
        # Fetch params directly from config when initialized
        self.params = config.model_hyperparameters.xgb_reg
        self.model = XGBRegressor(**self.params)
    
    def fit(self, X_train: pd.DataFrame, y_train: pd.DataFrame, X_val: pd.DataFrame=None,y_val:pd.DataFrame=None):
        """
        Fits the model. Uses validation set for early stopping if proviede,
        """
        if X_val is not None and y_val is not None:
            # XGBoost allows evaluating against a validation set during training
            self.model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False
            )
        else:
            self.model.fit(X_train, y_train)
        
        self.is_fitted_ = True 
        return self

    def predict(self,X):
        return self.model.predict(X)
    
    def get_model(self):
        return self.model