"""Entry point for the Hostage Chess server.

Usage: python -m src <port>
"""

import sys

from src.server.app import run_server


def main() -> None:
    """Parse command line arguments and start the server."""
    if len(sys.argv) != 2:
        print("Usage: python -m src <port>")
        sys.exit(1)

    try:
        port = int(sys.argv[1])
    except ValueError:
        print("Error: Port must be a number")
        sys.exit(1)

    run_server(port)


if __name__ == "__main__":
    main()
