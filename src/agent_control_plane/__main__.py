"""Command-line entry point for the API service."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "agent_control_plane.api:create_app_from_environment",
        host="0.0.0.0",
        port=8000,
        factory=True,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
