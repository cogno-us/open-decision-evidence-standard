from __future__ import annotations

import argparse
import json
import sys

from .common import dump_json, load_json
from .exporter import export_cognous_stack_package
from .recipient_validator import evaluate_recipient_package
from .schema_validation import validate_record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="odes")
    sub = parser.add_subparsers(dest="cmd", required=True)

    export = sub.add_parser("export-cognous")
    export.add_argument("--manifest", required=True)
    export.add_argument("--reconstruction", required=True)
    export.add_argument("--out", required=True)
    export.add_argument("--relying-party", default="recipient.example.org")
    export.add_argument("--purpose", default="audit")
    export.add_argument("--expires-at", default="2027-01-01T00:00:00Z")

    validate = sub.add_parser("validate-record")
    validate.add_argument("record")

    recipient = sub.add_parser("recipient-validate")
    recipient.add_argument("package")
    recipient.add_argument("--policy", required=True)
    recipient.add_argument("--out")

    args = parser.parse_args(argv)
    if args.cmd == "export-cognous":
        package = export_cognous_stack_package(load_json(args.manifest), load_json(args.reconstruction), relying_party=args.relying_party, purpose=args.purpose, expires_at=args.expires_at)
        dump_json(package, args.out)
        return 0
    if args.cmd == "validate-record":
        value = load_json(args.record)
        record = value.get("record", value) if isinstance(value, dict) else value
        validate_record(record)
        return 0
    if args.cmd == "recipient-validate":
        result = evaluate_recipient_package(load_json(args.package), load_json(args.policy))
        if args.out:
            dump_json(result, args.out)
        else:
            json.dump(result, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
