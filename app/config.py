# app\config.py
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from dataclasses import dataclass

FILES_DIR = Path("files")

@dataclass
class EnvConfig:
    mode: str
    secret_key: str
    binance_api_key: str
    binance_api_secret: str
    debug: bool

# Internal cache for singleton behavior
_env_cache: Optional[EnvConfig] = None

# Encapsulate environment variable loading
def load_env_vars() -> EnvConfig:
    """
    Load and cache environment variables only once.
    """
    mode = os.getenv("MODE", "test").lower()
    
    global _env_cache
    if _env_cache is not None:
        return _env_cache
    
    if(mode != "test") :
        # Paths to .env files
        root_dir = Path(__file__).resolve().parent.parent
        env_path = root_dir / ".env"
        env_local_path = root_dir / ".env.local"
        env_prod_path = root_dir / ".env.prod"
        
        print(env_prod_path)

        # Load in order: .env → .env.local → .env.prod if MODE=prod
        load_dotenv(env_path, override=True)
        load_dotenv(env_local_path, override=True)
        
        if mode == 'prod':
            load_dotenv(env_prod_path, override=True)

    # Validate essential variables
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        raise EnvironmentError("SECRET_KEY is missing in the environment variables.")
    
    _env_cache = EnvConfig(
        mode=mode,
        secret_key=os.getenv("SECRET_KEY", "dummy"),
        binance_api_key=os.getenv("BINANCE_API_KEY", "BINANCE_API_KEY"),
        binance_api_secret=os.getenv("BINANCE_API_SECRET", "BINANCE_API_SECRET"),
        debug=os.getenv("DEBUG", "false").lower() == "true",
    )

    return _env_cache