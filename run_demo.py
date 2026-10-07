"""Demo entrypoint for running GemmaSWE CLI and Benchmark."""

import sys
from gemmaswe.cli import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Default run benchmark if no arguments passed
        sys.argv.append("benchmark")
    main()
