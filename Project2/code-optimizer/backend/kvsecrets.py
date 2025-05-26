"""
Centralised, cached secret retrieval.
Secrets come from two sources:

1. Environment variables (always)
2. Azure Key Vault, *once per worker*, using those env vars.

Required env vars
─────────────────
VAULT_NAME              e.g. 'BDCvault'
AZURE_CLIENT_ID
AZURE_CLIENT_SECRET
AZURE_TENANT_ID
AZURE_DEPLOYMENT
LANGFUSE_HOST
"""

from functools import lru_cache
import logging
import os

from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient

_LOGGER = logging.getLogger(__name__)


@lru_cache
def _kv_client() -> SecretClient:
    vault_name = os.getenv("VAULT_NAME")
    if not vault_name:
        raise EnvironmentError("VAULT_NAME env var not set")

    credential = ClientSecretCredential(
        tenant_id=os.getenv("AZURE_TENANT_ID"),
        client_id=os.getenv("AZURE_CLIENT_ID"),
        client_secret=os.getenv("AZURE_CLIENT_SECRET"),
    )
    return SecretClient(vault_url=f"https://{vault_name}.vault.azure.net", credential=credential)


@lru_cache
def get_secret(name: str) -> str:
    """Fetch once per process via lru_cache."""
    _LOGGER.debug("Fetching secret %s from Key Vault", name)
    return _kv_client().get_secret(name).value


def prime_langfuse_env() -> None:
    """Set LANGFUSE_* only once."""
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", get_secret("LANGFUSE-PUBLIC-KEY"))
    os.environ.setdefault("LANGFUSE_SECRET_KEY", get_secret("LANGFUSE-SECRET-KEY"))

