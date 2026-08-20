import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.backend.services.db.models import ModelRegistry
from app.backend.services.logging_manager import database_logger

def register_new_model(db: Session, version: str, dataset_version: str, val_nse: float, val_rmse: float, hyperparams_dict: dict, active: bool = False):
    """
    Inserts a newly trained model version into the registry database.
    """
    hyper_str = json.dumps(hyperparams_dict)
    
    # Check if this version already exists
    exists = db.query(ModelRegistry).filter(ModelRegistry.model_version == version).first()
    if exists:
        database_logger.warning(f"Model version {version} already registered. Skipping insert.")
        return exists
        
    status = "active" if active else "staged"
    
    if active:
        # Demote current active models
        db.query(ModelRegistry).filter(ModelRegistry.deployment_status == "active").update(
            {"deployment_status": "staged"}
        )
        
    new_model = ModelRegistry(
        model_version=version,
        training_date=datetime.utcnow(),
        dataset_version=dataset_version,
        val_nse=float(val_nse),
        val_rmse=float(val_rmse),
        hyperparameters_json=hyper_str,
        deployment_status=status
    )
    db.add(new_model)
    db.commit()
    database_logger.info(f"Registered model version {version} in database. Status: {status}")
    return new_model

def get_active_model_details(db: Session):
    """
    Retrieves the currently active deployment model metadata.
    """
    return db.query(ModelRegistry).filter(ModelRegistry.deployment_status == "active").first()

def rollback_to_version(db: Session, version: str):
    """
    Swaps active deployment flag to a previously trained model version.
    """
    target = db.query(ModelRegistry).filter(ModelRegistry.model_version == version).first()
    if not target:
        database_logger.error(f"Cannot rollback: version {version} not found in database registry.")
        return False
        
    # Demote current active
    db.query(ModelRegistry).filter(ModelRegistry.deployment_status == "active").update(
        {"deployment_status": "rolled_back"}
    )
    
    target.deployment_status = "active"
    db.commit()
    database_logger.info(f"Swapped deployment active model version to {version} (Rollback).")
    return True
