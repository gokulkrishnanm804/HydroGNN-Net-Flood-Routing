import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
SessionLocal = None

def load_dotenv(project_dir):
    env_path = os.path.join(project_dir, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

def get_db_url():
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    project_dir = os.path.dirname(os.path.dirname(backend_dir))
    load_dotenv(project_dir)
    
    url = os.getenv("DATABASE_URL", "sqlite:///hydrognn.db")
    if url.startswith("sqlite:///"):
        # Resolve SQLite path relative to project root
        db_file = url.replace("sqlite:///", "")
        if not os.path.isabs(db_file):
            db_file = os.path.join(project_dir, db_file)
        url = f"sqlite:///{db_file}"
    return url

def initialize_database():
    global SessionLocal
    url = get_db_url()
    
    # SQLite connection requires check_same_thread=False
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    
    engine = create_engine(url, connect_args=connect_args)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized. Engine bind target: {url}")
    return engine

def get_db():
    if SessionLocal is None:
        initialize_database()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
