"""Allow `python -m gas_auditor.web` as an alternative to `gas-audit-web`."""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
