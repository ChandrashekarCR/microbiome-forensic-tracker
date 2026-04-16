import mlflow
import mlflow.xgboost
import pandas as pd
import numpy as np
from xgboost import XGBRegressor, XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

# Local imports

from ml.data_loading import DatabaseRSA
from ml.features import ZeroColumnFilter, MicrobiomeFeatureEngineer
from ml.models import load_and_prep_data, TrainTestSplit, XGBoostCoordinateModel
from ml.config import config
from sklearn.metrics import mean_absolute_error

def run_regression_pipeline(df):
    mlflow.set_experiment(config.mlflow.experiment_name)

    # Initialize splitter
    splitter = TrainTestSplit(df, n_splits=5)
    
    fold_scores = []

    with mlflow.start_run(run_name="predict_coordinates_cv"):
        
        for fold, (train_idx, val_idx) in enumerate(splitter.stratifed_zone_data_split()):
            print(f"--- Processing Fold {fold+1}/5 ---")

            # 1. Get the fold data
            X_train, X_val, _, _, y_train_coords, y_val_coords = splitter.get_fold_data(train_idx, val_idx)

            # 2. Apply Feature Engineering
            # Must re-initialize for EVERY fold to prevent data leakage from validation sets mapping into train
            zcf = ZeroColumnFilter(min_prevalence=0.05)       
            engineer = MicrobiomeFeatureEngineer()

            print("Fitting feature pipeline...")
            X_train_filtered = zcf.fit_transform(X_train)
            X_val_filtered = zcf.transform(X_val)

            X_train_final = engineer.fit_transform(X_train_filtered)
            X_val_final = engineer.transform(X_val_filtered)

            # 3. Initialize and Train Model using encapsulation
            print("Training Coordinate XGBoost Regressor...")
            regressor = XGBoostCoordinateModel()
            regressor.fit(X_train_final, y_train_coords, X_val=X_val_final, y_val=y_val_coords)
            
            # 4. Evaluate Fold
            preds_val = regressor.predict(X_val_final)
            fold_mae = mean_absolute_error(y_val_coords, preds_val)
            fold_scores.append(fold_mae)
            
            print(f"Fold {fold+1} MAE: {fold_mae:.4f}")
            mlflow.log_metric(f"fold_{fold+1}_mae", fold_mae)
        
        # 5. Log Overall CV Metrics
        avg_mae = np.mean(fold_scores)
        print(f"\nCompleted Strategy CV. Average MAE: {avg_mae:.4f}")
        mlflow.log_metric("cv_avg_mae", avg_mae)
        
        # Log the config parameters and the final model from the last fold
        mlflow.log_params(config.model_hyperparameters.xgb_reg)
        mlflow.xgboost.log_model(regressor.get_model(), "xgboost_coordinate_cv_model")

#def run_classification_pipeline(df):
#    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
#    with mlflow.start_run(run_name="predict_zone"):
#        # 1. Prepare target and features
#        X = df.drop(columns=["sample_id", "latitude", "longitude", "zone"])
#        
#        le = LabelEncoder()
#        y = le.fit_transform(df["zone"])
#        
#        # 2. Split (Stratified to maintain class weights)
#        X_train, X_test, y_train, y_test = train_test_split(
#            X, y, stratify=y, test_size=TEST_SIZE, random_state=RANDOM_STATE
#        )
#        
#        # 3. Fit Feature Engineering (TRAIN ONLY)
#        print("Running Feature Engineering Pipeline (Zones)...")
#        zcf = ZeroColumnFilter(min_prevalence=0.05)
#        X_train_filtered = zcf.fit(X_train).transform(X_train)
#        X_test_filtered = zcf.transform(X_test)
#        
#        engineer = MicrobiomeFeatureEngineer()
#        X_train_final = engineer.fit(X_train_filtered).transform(X_train_filtered)
#        X_test_final = engineer.transform(X_test_filtered)
#        
#        # 4. Train Model
#        print("Training Zone XGBoost Classifier...")
#        # Number of classes needed for softprob objective
#        clf_params = XGB_CLF_PARAMS.copy()
#        clf_params["num_class"] = len(np.unique(y_train))
#        
#        model = XGBClassifier(**clf_params)
#        model.fit(X_train_final, y_train)
#        
#        # 5. Evaluate
#        preds = model.predict(X_test_final)
#        metrics = evaluate_classification(y_test, preds)
#        
#        # 6. Log to MLflow
#        mlflow.log_params(clf_params)
#        mlflow.log_metrics(metrics)
#        mlflow.xgboost.log_model(model, "xgboost_zone_model")
#        
#        print(f"Classification completed. Metrics: {metrics}")

if __name__ == "__main__":
    print("Loading data...")
    df = load_and_prep_data()
    
    print("\n========== REGRESSION PIPELINE ==========")
    run_regression_pipeline(df)
    
    #print("\n========== CLASSIFICATION PIPELINE ==========")
    #run_classification_pipeline(df)

