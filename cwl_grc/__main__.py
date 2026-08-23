"""Standalone entry: ``python -m cwl_grc`` or the ``cwl-grc`` console script."""

from __future__ import annotations

import json

import uvicorn

from cwl_grc.app import create_app
from cwl_grc.remote_access import loopback_server_bind, startup_next_action


def main() -> None:
    """Serve the local preview on loopback, requiring TLS when Keyverse is required."""
    try:
        settings = loopback_server_bind()
        uvicorn.run(create_app(), **settings)
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "next_action": startup_next_action(),
                }
            )
        )
        raise SystemExit(2) from exc


if __name__ == "__main__":  # pragma: no cover
    main()
