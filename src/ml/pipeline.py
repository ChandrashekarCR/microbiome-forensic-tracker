import mlflow
import mlflow.xgboost
import numpy as np


from ml.features import ZeroColumnFilter, MicrobiomeFeatureEngineer
from ml.models import load_and_prep_data, TrainTestSplit, XGBoostCoordinateModel
from ml.config import config
from sklearn.metrics import mean_absolute_error

def run_regression_pipeline(df):
    mlflow.set_experiment(config.mlflow.experiment_name)

    # Initialize splitter for splitting the data
    splitter = TrainTestSplit(df, n_splits=5)
    
    fold_scores = []

    with mlflow.start_run(run_name="predict_coordinates_cv"):
        
        for fold, (train_idx, val_idx) in enumerate(splitter.stratifed_zone_data_split()):
            print(f"Processing Fold {fold+1}/5")

            # 1. Get the fold data
            X_train, X_val, _, _, y_train_coords, y_val_coords = splitter.get_fold_data(train_idx, val_idx)

            # 2. Apply Feature Engineering
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

if __name__ == "__main__":
    print("Loading data...")
    df = load_and_prep_data()
    
    print("\n========== REGRESSION PIPELINE ==========")
    run_regression_pipeline(df)
    
    #print("\n========== CLASSIFICATION PIPELINE ==========")
    #run_classification_pipeline(df)

