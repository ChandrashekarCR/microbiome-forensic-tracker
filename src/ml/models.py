import pandas as pd
from pyproj import Transformer
from sklearn.model_selection import GroupKFold, LeaveOneOut, RepeatedKFold, RepeatedStratifiedKFold, StratifiedKFold, train_test_split
from enum import Enum


from malmo_samples.db_reader import DatabaseCreate
from ml.config import config
from ml.data_loading import DatabaseRSA

from abc import ABC, abstractmethod
from sdv.metadata import SingleTableMetadata
from sdv.single_table import TVAESynthesizer


# Load the data from the SQL database
def load_and_prep_data() -> pd.DataFrame:
    """Load from SQLite, merge metadata, drop NaNs."""
    samples = DatabaseCreate(db=config.database.path)
    rsa = DatabaseRSA(db=config.database.path, db_table=config.database.table)
    df = rsa.merge_data(samples.get_samples(), rsa.sql_to_clean())

    return df


# Differents methods of splitting data
class TrainTestSplit:
    def __init__(self, df: pd.DataFrame, n_splits: int = 4, test_size: float = 0.2):
        X_all = df.drop(columns=["latitude", "longitude", "zone", "sample_id"], axis=1)
        y_zone_all = df["zone"]

        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True)
        x_m, y_m = transformer.transform(
            df["longitude"].to_numpy(),
            df["latitude"].to_numpy(),
        )

        new_cols = pd.DataFrame(
            {"X_meters": x_m, "Y_meters": y_m},
            index=df.index,
        )

        df = pd.concat([df, new_cols], axis=1)

        # Pass in everything and let the user decided on which he wants to train on. Accordingly the evaution metrics are set.
        y_coords_all = df[["X_meters", "Y_meters", "latitude", "longitude"]]

        self.n_splits = n_splits

        # 1. Slice off the 20% blind test set first. Stratify by zone.
        (self.X_cv, self.X_test, self.y_cv_zone, self.y_test_zone, self.y_cv_coords, self.y_test_coords) = train_test_split(
            X_all, y_zone_all, y_coords_all, test_size=test_size, stratify=y_zone_all, random_state=config.data_splitting.random_state
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

    def __init__(self, epochs:int=300, batch_size:int=32):
        self.epochs = epochs
        self.batch_size = batch_size
        self.synthesizer = None
        self._x_cols = None
        self._y_cols = None

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
            batch_size=self.batch_size
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
