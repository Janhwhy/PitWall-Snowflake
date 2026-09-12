"""
snowflake_client.py
--------------------
Key-pair-authenticated Snowflake connection, shared by the migration
scripts and (once cut over) the API's structured-data + Cortex Search
queries.

Requires these vars in .env (see .env.example):
    SNOWFLAKE_ACCOUNT
    SNOWFLAKE_USER
    SNOWFLAKE_ROLE
    SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_DATABASE
    SNOWFLAKE_SCHEMA
    SNOWFLAKE_PRIVATE_KEY_PATH   -- path to the unencrypted PKCS8 .p8 file
"""

import os
import pathlib

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent


def _load_private_key_bytes() -> bytes:
    """
    Load the key-pair-auth private key from either a local file
    (SNOWFLAKE_PRIVATE_KEY_PATH — local dev, the file is git-ignored) or
    raw PEM content in an env var (SNOWFLAKE_PRIVATE_KEY — for deploy
    targets like Render, where git-ignored files never reach the build).
    """
    raw_pem = os.getenv("SNOWFLAKE_PRIVATE_KEY")
    if raw_pem:
        pem_bytes = raw_pem.encode("utf-8").replace(b"\\n", b"\n")
    else:
        key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
        if not key_path:
            raise ValueError(
                "Set either SNOWFLAKE_PRIVATE_KEY (raw PEM) or "
                "SNOWFLAKE_PRIVATE_KEY_PATH (file path) in .env"
            )
        with open(ROOT_DIR / key_path, "rb") as f:
            pem_bytes = f.read()

    p_key = serialization.load_pem_private_key(
        pem_bytes,
        password=None,
        backend=default_backend(),
    )

    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def get_connection() -> snowflake.connector.SnowflakeConnection:
    """Open a new Snowflake connection using key-pair auth from .env."""
    required = [
        "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE",
        "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA",
    ]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        raise ValueError(f"Missing required env var(s): {', '.join(missing)}")

    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        private_key=_load_private_key_bytes(),
        role=os.getenv("SNOWFLAKE_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
    )


if __name__ == "__main__":
    print("=== snowflake_client.py smoke test ===")
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute("SELECT CURRENT_VERSION(), CURRENT_WAREHOUSE(), CURRENT_DATABASE()")
        print(cur.fetchone())
    finally:
        con.close()
