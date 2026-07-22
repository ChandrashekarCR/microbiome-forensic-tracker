import pandas as pd
from pyproj import Transformer
from sklearn.model_selection import GroupKFold, LeaveOneOut, RepeatedKFold, RepeatedStratifiedKFold, StratifiedKFold, train_test_split
from enum import Enum


from malmo_samples.db_reader import DatabaseCreate
from ml.config import config
from ml.data_loading import DatabaseRSA
from sklearn.cluster import DBSCAN

from abc import ABC, abstractmethod
from sdv.metadata import SingleTableMetadata
from sdv.single_table import TVAESynthesizer
import torch


# Load the data from the SQL database
def load_and_prep_data() -> pd.DataFrame:
    """Load from SQLite, merge metadata, drop NaNs."""
    samples = DatabaseCreate(db=config.database.path)
    rsa = DatabaseRSA(db=config.database.path, db_table=config.database.table)
    df = rsa.merge_data(samples.get_samples(), rsa.sql_to_clean())

    return df


# Differents methods of splitting data
class TrainTestSplit:
    def __init__(self, df: pd.DataFrame, n_splits: int = 4, 
                 test_size: float = 0.2,
                 site_threshold_meters: float = 15.0,
                 random_state: int = config.data_splitting.random_state):


        self.n_splits = n_splits
        self.site_threshold_metres = site_threshold_meters


        # Make a copy and project coordinates to meters
        df = df.copy()

        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True)
        x_m, y_m = transformer.transform(
            df["longitude"].to_numpy(),
            df["latitude"].to_numpy(),
        )

        df['X_meters'] = x_m
        df['Y_meters'] = y_m

        # Create site ids using DBSCAN clustering algorithm 
        coords = df[['X_meters','Y_meters']].to_numpy()
        clustering = DBSCAN(eps=site_threshold_meters,min_samples=1,metric='euclidean')
        df['site_id'] = clustering.fit_predict(coords)
        df['site_id'] = df['site_id'].apply(lambda x: f'SITE_{x:04d}')

        # Store the site info
        self.site_counts = df['site_id'].value_counts()

        # Prepare features and targets
        drop_cols = ["latitude", "longitude", "zone", "sample_id","site_id","X_meters","Y_meters"]
        X_all = df.drop(columns=drop_cols, axis=1)
        y_zone_all = df["zone"]


        # Pass in everything and let the user decided on which he wants to train on. Accordingly the evaution metrics are set.
        y_coords_all = df[["X_meters", "Y_meters", "latitude", "longitude"]]
        site_ids_all = df['site_id']

        # Split by site_id and not by random rows
        # Get unique sites with their zones
        site_representatives = df.drop_duplicates(subset='site_id')[['site_id','zone']]

        # Stratify at the site level to preserve zone proporions
        train_sites, test_sites = train_test_split(site_representatives['site_id'],test_size=test_size,
                                                   stratify=site_representatives['zone'],random_state=random_state)

        # Get indices for train and test
        train_idx = df[df['site_id'].isin(train_sites)].index
        test_idx = df[df['site_id'].isin(test_sites)].index

        # Create train and test DataFrames
        df_train = df.loc[train_idx].reset_index(drop=True)
        df_test = df.loc[test_idx].reset_index(drop=True)
        
        # 5. Store train and test splits ---
        self.X_cv = df_train.drop(columns=drop_cols, axis=1)
        self.X_test = df_test.drop(columns=drop_cols, axis=1)
        
        self.y_cv_zone = df_train["zone"].reset_index(drop=True)
        self.y_test_zone = df_test["zone"].reset_index(drop=True)
        
        self.y_cv_coords = df_train[["X_meters", "Y_meters", "latitude", "longitude"]].reset_index(drop=True)
        self.y_test_coords = df_test[["X_meters", "Y_meters", "latitude", "longitude"]].reset_index(drop=True)
        
        self.cv_site_ids = df_train["site_id"].reset_index(drop=True)
        self.test_site_ids = df_test["site_id"].reset_index(drop=True)

    def groupkfold_site_split(self) -> list:
        """
        GroupKFold by site_id.
        All samples from the same site stay together in the same fold.
        This is TRUE spatial generalization and prevents data leakage.
        """
        gkf = GroupKFold(n_splits=self.n_splits)
        return list(gkf.split(self.X_cv, self.y_cv_zone, groups=self.cv_site_ids))

    def stratifed_zone_data_split(self) -> list:
        """
        Returns K-fold indices for stratified CV on zone on the remaining 80% data
        """
        skf = StratifiedKFold(n_splits=self.n_splits, shuffle=True, random_state=config.data_splitting.random_state)
        return list(skf.split(self.X_cv, self.y_cv_zone))

    def repeated_zone_data_split(self) -> list:
        """
        Return indices which are meant for regression tasks and not for classification tasks
        """
        rkf = RepeatedKFold(n_splits=self.n_splits, n_repeats=config.data_splitting.n_repeats, random_state=config.data_splitting.random_state)
        return list(rkf.split(self.X_cv))

    def repeated_stratified_zone_data_split(self) -> list:
        """
        Returns repeated stratified k-fold cv on the remaining 80% data
        """
        rskf = RepeatedStratifiedKFold(
            n_splits=self.n_splits, n_repeats=config.data_splitting.n_repeats, random_state=config.data_splitting.random_state
        )
        return list(rskf.split(self.X_cv, self.y_cv_zone))

    def leave_one_out_split(self) -> list:
        """
        Returns a list of indices which are from the 80% of the dataset and one is left out, rest is trained on
        """
        loocv = LeaveOneOut()
        return list(loocv.split(self.X_cv))

    def groupkfold_zone_split(self) -> list:
        """
        Hold out entire zone at a time. This will be true spatila generalization
        """
        gkf = GroupKFold(n_splits=self.n_splits)
        return list(gkf.split(self.X_cv, self.y_cv_zone, groups=self.y_cv_zone))

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

class BaseSynthesizer(ABC):
    """Abstract base for all synthetic data generators."""

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.DataFrame) -> None:
        pass

    @abstractmethod
    def generate(self, n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Returns (synthetic_X, synthetic_y)"""
        pass

class TVAEDataSynthesizer(BaseSynthesizer):
    """
    TVAE based synthesizer using SDV
    Fit on combined (X,y) to learn joint distribution
    """

    def __init__(self, epochs:int=300, batch_size:int=32, cuda: bool = True):
        self.epochs = epochs
        self.batch_size = batch_size
        self.synthesizer = None
        self._x_cols = None
        self._y_cols = None
        self.cuda = cuda and torch.cuda.is_available()

    def fit(self, X:pd.DataFrame, y:pd.DataFrame) -> None:
        self._x_cols = X.columns.tolist()
        self._y_cols = y.columns.to_list()

        # We need to combined this to a dataframe
        combined_df = pd.concat([X.reset_index(drop=True),y.reset_index(drop=True)],axis=1)

        # Initialize metadata class
        metadata = SingleTableMetadata()
        metadata.detect_from_dataframe(combined_df)
        for cols in self._y_cols:
            metadata.update_column(column_name=cols,sdtype="numerical")
        
        # Initialize the synthesizer
        self.synthesizer = TVAESynthesizer(
            metadata,
            enforce_min_max_values=True,
            epochs=self.epochs,
            batch_size=self.batch_size,
            enable_gpu=self.cuda
        )

        self.synthesizer.fit(combined_df)
    
    def generate(self, n:int) -> tuple[pd.DataFrame,pd.DataFrame]:
        synthetic = self.synthesizer.sample(num_rows=n)

        return synthetic[self._x_cols].reset_index(drop=True), \
                synthetic[self._y_cols].reset_index(drop=True)
        


class DataRoute(str, Enum):
    RAW = "raw"               # only real data (your current baseline)
    SYNTHETIC = "synthetic"   # only synthetic data
    COMBINED = "combined"     # real + synthetic (most useful)

# df = load_and_prep_data()
# splitter = TrainTestSplit(df)
#
# for fold, (train_idx,val_idx) in enumerate(splitter.repeated_zone_data_split()):
#    # Number of folds , default=4
#    X_train, X_val, y_train_zone, y_val_zone, y_train_coords, y_val_coords = splitter.get_fold_data(train_idx,val_idx)
#
#    print(X_train)
#    print(y_train_coords)
