"""Allow `python -m gas_auditor` as an alternative to the `gas-audit` script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
