import os 
from dotenv import load_dotenv
load_dotenv()


def to_bool(value, default=False):
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB = os.getenv("POSTGRES_DB", "akili_market_intel")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    SQLALCHEMY_DATABASE_URI = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4.1-mini")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    WATCHLIST = [x.strip() for x in os.getenv("WATCHLIST", "NFLX,DIS,WBD,ROKU,SPOT").split(",") if x.strip()]

    DEBUG = to_bool(os.getenv("DEBUG"), default=True)
    TESTING = to_bool(os.getenv("TESTING"), default=False)
