import argparse
import json

from .config import SecretaryConfig
from .koboldcpp import KoboldCppClient


def main() -> None:
    parser = argparse.ArgumentParser(prog="pysecretary")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="start the assistant")
    subparsers.add_parser("inspect-kobold", help="print the discovered KoboldCPP API profile")
    prototype_parser = subparsers.add_parser("prototype-ui", help="start the automatic voice smoothing prototype UI")
    prototype_parser.add_argument("--host", default=None, help="host for the prototype UI")
    prototype_parser.add_argument("--port", type=int, default=None, help="port for the prototype UI")
    prototype_parser.add_argument("--mock", action="store_true", help="run with scripted demo turns instead of live audio/KoboldCPP")
    args = parser.parse_args()

    if args.command == "inspect-kobold":
        config = SecretaryConfig.from_env()
        client = KoboldCppClient.from_config(config)
        print(json.dumps(client.profile.to_dict(), indent=2))
        return

    if args.command == "prototype-ui":
        from .web.server import run_prototype_server

        config = SecretaryConfig.from_env()
        host = args.host or config.prototype_host
        port = args.port or config.prototype_port
        if args.mock:
            from .prototype import create_demo_controller

            run_prototype_server(host=host, port=port, config=config, controller=create_demo_controller(config))
        else:
            run_prototype_server(host=host, port=port, config=config)
        return

    from .app import main as run_app

    run_app()


if __name__ == "__main__":
    main()
