#!/usr/bin/env python3
"""Convert RFC 4180 CSV records to one canonical JSON array per line."""

import csv
import json
import sys


def main(argv):
    if len(argv) != 2:
        print("usage: csv_records.py INPUT.csv", file=sys.stderr)
        return 2
    try:
        with open(argv[1], "r", encoding="utf-8", newline="") as source:
            for row in csv.reader(source, strict=True):
                # Escaping produces one physical line per logical record, even
                # when a VARCHAR contains a newline, ready for external sort.
                print(json.dumps(row, ensure_ascii=True, separators=(",", ":")))
    except (OSError, UnicodeError, csv.Error) as exc:
        print("csv_records.py: {}".format(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
