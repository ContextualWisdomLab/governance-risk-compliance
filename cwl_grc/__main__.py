"""Standalone entry: ``python -m cwl_grc`` or the ``cwl-grc`` console script."""

from __future__ import annotations

import os

import uvicorn

from cwl_grc.app import create_app


def main() -> None:
    """Serve the local developer preview on loopback, defaulting to a local store.

    This module entrypoint is the dedicated local-development path. It alone
    supplies the local SQLite store and ``development`` ownership profile when
    the environment omits them; every other entrypoint requires both settings.
    """
    port = int(os.environ.get("PORT", "8080"))
    database_url = os.environ.get("CWL_GRC_DATABASE_URL", "sqlite:///grc_product.sqlite")
    schema_mode = os.environ.get("CWL_GRC_SCHEMA_MODE", "development")
    uvicorn.run(
        create_app(database_url=database_url, schema_mode=schema_mode),
        host="127.0.0.1",
        port=port,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
