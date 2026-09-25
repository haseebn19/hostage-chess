"""Entry point for the Hostage Chess server: `hostage-chess <port>` or `python -m hostage_chess <port>`."""

import argparse

from hostage_chess.server.app import run_server


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hostage-chess", description="Run the Hostage Chess server."
    )
    parser.add_argument("port", type=int, help="the port to listen on, such as 8080")
    run_server(parser.parse_args().port)


if __name__ == "__main__":
    main()
