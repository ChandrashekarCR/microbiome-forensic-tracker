import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, StratifiedKFold
from xgboost import XGBRegressor, XGBClassifier

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

# Stratifier train test and validation
class TrainTestSplit:
    def __init__(self,df:pd.DataFrame,n_splits: int=5):
        self.X = df.drop(columns=["sample_id", "latitude", "longitude", "zone"],axis=1)
        self.y_zone = df['zone']
        self.y_coords = df[['latitude','longitude']]
        self.n_splits = n_splits
    
    def stratifed_zone_data_split(self) -> list:
        """
        Returns K-fold indices for stratified CV on zone
        """
        skf = StratifiedKFold(n_splits=self.n_splits,shuffle=True,random_state=config.data_splitting.random_state)
        
        return list(skf.split(self.X,self.y_zone))
    
    def get_fold_data(self,train_idx:int,val_idx:int) -> pd.DataFrame:
        """
        Get X,y for a specific fold
        """
        X_train, X_val = self.X.iloc[train_idx], self.X.iloc[val_idx]
        y_train_zone, y_val_zone = self.y_zone.iloc[train_idx], self.y_zone.iloc[val_idx]
        y_train_coords, y_val_coords = self.y_coords.iloc[train_idx], self.y_coords.iloc[val_idx]

        return X_train, X_val, y_train_zone, y_val_zone, y_train_coords, y_val_coords
    

class XGBoostCoordinateModel:
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
        return self

    def predict(self,X):
        return self.model.predict(X)
    
    def get_model(self):
        return self.model