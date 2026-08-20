import os
import logging

def get_project_root():
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    project_dir = os.path.dirname(os.path.dirname(backend_dir))
    return project_dir

def setup_logger(name, log_file, level=logging.INFO):
    project_root = get_project_root()
    logs_dir = os.path.join(project_root, "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
        
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_path = os.path.join(logs_dir, log_file)
    handler = logging.FileHandler(file_path)
    handler.setFormatter(formatter)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers if setup_logger is called multiple times
    if not logger.handlers:
        logger.addHandler(handler)
        
    return logger

# Initialize production separate loggers
api_logger = setup_logger("api", "api.log")
scheduler_logger = setup_logger("scheduler", "scheduler.log")
prediction_logger = setup_logger("prediction", "prediction.log")
training_logger = setup_logger("training", "training.log")
database_logger = setup_logger("database", "database.log")
alerts_logger = setup_logger("alerts", "alerts.log")
error_logger = setup_logger("error", "errors.log", level=logging.WARNING)

# Hook standard logs and uncaught errors to error_logger
class ErrorCapturingHandler(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            error_logger.handle(record)

# Attach error capture to all created loggers
for logger_obj in [api_logger, scheduler_logger, prediction_logger, training_logger, database_logger, alerts_logger]:
    logger_obj.addHandler(ErrorCapturingHandler())
