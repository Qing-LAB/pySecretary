import argparse
import json

from .config import SecretaryConfig
from .koboldcpp import KoboldCppClient


def main() -> None:
    parser = argparse.ArgumentParser(prog="pysecretary")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="start the assistant")
    subparsers.add_parser("inspect-kobold", help="print the discovered KoboldCPP API profile")
    args = parser.parse_args()

    if args.command == "inspect-kobold":
        config = SecretaryConfig.from_env()
        client = KoboldCppClient.from_config(config)
        print(json.dumps(client.profile.to_dict(), indent=2))
        return

    from .app import main as run_app

    run_app()


if __name__ == "__main__":
    main()
