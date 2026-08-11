"""Command-line entry point for the API service."""

import uvicorn


def main() -> None:
    uvicorn.run("agent_control_plane.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()
