import mlflow
import numpy as np
from sklearn.pipeline import Pipeline

from ml.features import ZeroColumnFilter, MicrobiomeFeatureEngineer
from ml.models import load_and_prep_data, TrainTestSplit, XGBoostCoordinateModel
from ml.config import config
from ml.evaluation import evaluate_coordinates


def build_pipeline(use_network_features=True):
    """
    A funtion to easily add and remove steps in the ML pipeline.
    """
    steps = []

    steps.append(("zeros_filter", ZeroColumnFilter(min_prevalence=0.05)))

    if use_network_features:
        steps.append(('network_features',MicrobiomeFeatureEngineer()))
    
    # Standard XGBoost Regression
    steps.append(("model",XGBoostCoordinateModel()))

    return Pipeline(steps)

def run_regression_pipeline(df,use_network=False):
    mlflow.set_experiment(config.mlflow.experiment_name)

    # Initialize splitter for splitting the data
    splitter = TrainTestSplit(df, n_splits=3)
    
    fold_scores = []

    with mlflow.start_run(run_name="predict_coordinates_cv"):
        
        for fold, (train_idx, val_idx) in enumerate(splitter.stratifed_zone_data_split()):
            print(f"Processing Fold {fold+1}/5")

            # 1. Get the fold data
            X_train, X_val, y_train_zone, y_val_zone, y_train_coords, y_val_coords = splitter.get_fold_data(train_idx, val_idx)

            # 2. Build Pipeline (Create a fresh pipeline each fold to avoid data leakage)
            pipeline = build_pipeline(use_network_features=use_network)

            # 3. Initialize and Train Model using encapsulation
            print("Fitting Pipeline")
            pipeline.fit(X_train,y_train_coords)

            # 4. Predict on validation
            preds_val = pipeline.predict(X_val)
            
            # 5. Custom evaluation script
            metrics = evaluate_coordinates(
                y_true_lat=y_val_coords["latitude"].values,
                y_true_lon=y_val_coords["longitude"].values,
                y_pred_lat=preds_val[:, 0],
                y_pred_lon=preds_val[:, 1],
                zones_true=y_val_zone.values
            )
            
            fold_mae = metrics["mean_error_km"]
            fold_scores.append(fold_mae)
            
            print(f"Fold {fold+1} Mean Haversine Error: {fold_mae:.2f} km")
            
            # Log all your custom metrics for this fold
            for k, v in metrics.items():
                mlflow.log_metric(f"fold_{fold+1}_{k}", v)
        
        # 6. Log Overall CV Metrics
        avg_mae = np.mean(fold_scores)
        print(f"\nCompleted Strategy CV. Average MAE: {avg_mae:.4f}")
        mlflow.log_metric("cv_avg_mae", avg_mae)
        
        # 7. Evaluate the final model on the data it has never seen before
        X_test, y_test_zone, y_test_coords = splitter.get_test_data()

        test_preds = pipeline.predict(X_test)

        test_metrics = evaluate_coordinates(
            y_true_lat=y_test_coords['latitude'].values,
            y_true_lon=y_test_coords['longitude'].values,
            y_pred_lat=test_preds[:,0],
            y_pred_lon=test_preds[:,1],
            zones_true=y_test_zone.values
        )

        for metric,value in test_metrics.items():
            print(metric,value)

        # Log the config parameters and the final model from the last fold
        mlflow.log_params(config.model_hyperparameters.xgb_reg)
        # Log the final pipeline (from the last fold) so it can be deployed easily
        mlflow.sklearn.log_model(pipeline, "final_coordinate_pipeline")

if __name__ == "__main__":
    print("Loading data...")
    df = load_and_prep_data()
    
    print("\n========== REGRESSION PIPELINE ==========")
    run_regression_pipeline(df)
    #run_regression_experiment(df)

    #print("\n========== CLASSIFICATION PIPELINE ==========")
    #run_classification_pipeline(df)

