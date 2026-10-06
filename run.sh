#!/bin/sh

set -e

if [ "$1" = "test" ]; then
    python3 -m unittest discover -s tests -v
    exit 0
fi

python3 -m src.main "$@"
