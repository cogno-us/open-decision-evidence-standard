# Contributing

Contributions are welcome through issues and pull requests.

Useful contributions include:

- missing fields
- unnecessary fields
- terminology improvements
- sector-specific examples
- privacy risks
- security risks
- conformance requirements
- use-case analysis
- existing related standards

Please keep proposals vendor-neutral, precise, and grounded in open implementation concerns.

## Contributor representation

By contributing, contributors represent that they have the right to submit the contribution and agree that contributions may be incorporated into an open, freely implementable specification under Apache License 2.0.

A formal CLA or standards contribution framework may be introduced before v1.0.

## Local test runs

Run the suite from a checkout with `PYTHONPATH=src python -m pytest -q`. Supported interpreters are Python 3.11, 3.12, 3.13 and 3.14; run it under each one you have before a change that touches time parsing, schema interpretation or the validators (Python 3.14 reads an hour of `24` where earlier versions refuse it, which is why the instant shape refuses it itself). The repository's workflow runs a subset; the local runs are the wider check.

