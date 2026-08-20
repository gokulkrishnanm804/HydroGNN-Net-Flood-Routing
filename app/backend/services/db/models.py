from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Date, Text
from sqlalchemy.orm import relationship
from app.backend.services.db.connection import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    role = Column(String(50), default="public")
    password_hash = Column(String(200), nullable=False)


class RiverStation(Base):
    __tablename__ = "river_stations"
    
    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    river = Column(String(100), nullable=False)
    district = Column(String(100), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    dem_elevation = Column(Float, nullable=False)
    danger_level = Column(Float, nullable=False)
    
    # Relationships
    reservoirs = relationship("Reservoir", back_populates="station")
    levels = relationship("RiverLevel", back_populates="station")
    predictions = relationship("Prediction", back_populates="station")
    alerts = relationship("Alert", back_populates="station")
    rainfall_records = relationship("Rainfall", back_populates="station")
    weather_records = relationship("Weather", back_populates="station")


class Reservoir(Base):
    __tablename__ = "reservoirs"
    
    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    capacity_mcft = Column(Float, nullable=False)
    nearest_station_id = Column(String(50), ForeignKey("river_stations.id"))
    
    station = relationship("RiverStation", back_populates="reservoirs")


class Rainfall(Base):
    __tablename__ = "rainfall"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(String(50), ForeignKey("river_stations.id"), nullable=False)
    ts = Column(DateTime, nullable=False)
    value_mm = Column(Float, nullable=False)
    source = Column(String(50), default="observed")
    
    station = relationship("RiverStation", back_populates="rainfall_records")


class Weather(Base):
    __tablename__ = "weather"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(String(50), ForeignKey("river_stations.id"), nullable=False)
    ts = Column(DateTime, nullable=False)
    temp = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    wind_speed = Column(Float, nullable=False)
    source = Column(String(50), default="observed")  # Issue #4 fix
    
    station = relationship("RiverStation", back_populates="weather_records")


class RiverLevel(Base):
    __tablename__ = "river_levels"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(String(50), ForeignKey("river_stations.id"), nullable=False)
    ts = Column(DateTime, nullable=False)
    level_m = Column(Float, nullable=False)
    discharge_cumecs = Column(Float, nullable=False)
    storage_pct = Column(Float, default=0.0)
    release = Column(Float, default=0.0)
    source = Column(String(50), default="observed")  # Issue #4 fix
    
    station = relationship("RiverStation", back_populates="levels")


class Prediction(Base):
    __tablename__ = "predictions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(String(50), ForeignKey("river_stations.id"), nullable=False)
    issued_at = Column(DateTime, nullable=False)
    horizon_hours = Column(Integer, nullable=False)
    predicted_level = Column(Float, nullable=False)
    uncertainty = Column(Float, nullable=False)
    flood_probability = Column(Float, nullable=False)
    severity_class = Column(String(50), default="Safe")
    confidence = Column(Float, default=1.0)
    arrival_time_hours = Column(Float, default=0.0)
    
    station = relationship("RiverStation", back_populates="predictions")


class Alert(Base):
    __tablename__ = "alerts"
    
    id = Column(String(100), primary_key=True)
    station_id = Column(String(50), ForeignKey("river_stations.id"), nullable=False)
    prediction_id = Column(Integer, nullable=True)
    sent_at = Column(DateTime, nullable=False)
    channel = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String(50), default="WARNING")
    
    station = relationship("RiverStation", back_populates="alerts")


class SatelliteImage(Base):
    __tablename__ = "satellite_images"
    
    id = Column(String(50), primary_key=True)
    station_id = Column(String(50), ForeignKey("river_stations.id"))
    capture_date = Column(Date, nullable=False)
    source = Column(String(50), nullable=False)
    storage_path = Column(String(200), nullable=False)


class GisLayer(Base):
    __tablename__ = "gis_layers"
    
    id = Column(String(50), primary_key=True)
    layer_name = Column(String(100), nullable=False)
    geometry_type = Column(String(50), nullable=False)
    geojson_or_ref = Column(Text, nullable=False)


class DataVersion(Base):
    __tablename__ = "data_versions"
    
    version_id = Column(String(50), primary_key=True)
    api_source = Column(String(100), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    data_quality_score = Column(Float, default=1.0)
    missing_values_count = Column(Integer, default=0)
    validation_status = Column(String(50), default="VALID")


class FeatureStore(Base):
    __tablename__ = "feature_store"
    
    feature_id = Column(String(100), primary_key=True)
    station_id = Column(String(50), ForeignKey("river_stations.id"), nullable=False)
    ts = Column(DateTime, nullable=False)
    rain_norm = Column(Float, nullable=False)
    level_norm = Column(Float, nullable=False)
    discharge_norm = Column(Float, nullable=False)
    soil_moisture = Column(Float, nullable=False)
    split_type = Column(String(50), default="inference") # train, val, test, inference
    version_id = Column(String(50), ForeignKey("data_versions.version_id"), nullable=True)


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    
    model_version = Column(String(50), primary_key=True)
    training_date = Column(DateTime, nullable=False)
    dataset_version = Column(String(50), nullable=False)
    val_nse = Column(Float, nullable=False)
    val_rmse = Column(Float, nullable=False)
    hyperparameters_json = Column(Text, nullable=False)
    deployment_status = Column(String(50), default="staged") # active, staged, rolled_back
