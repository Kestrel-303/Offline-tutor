"""Run normalize_page over data/extracted/pages.jsonl and print counts only.

Never prints page text.
"""

import json
from collections import Counter
from pathlib import Path

from offline_tutor.normalize import normalize_page_with_stats

PAGES = Path(__file__).resolve().parent.parent / "data" / "extracted" / "pages.jsonl"


def main() -> None:
    processed = changed = joined = 0
    remaining: Counter[str] = Counter()
    with PAGES.open(encoding="utf-8") as f:
        for line in f:
            text = json.loads(line)["text"]
            result, joins = normalize_page_with_stats(text)
            processed += 1
            changed += result != text
            joined += joins
            remaining.update(ch for ch in result if ord(ch) > 127)
    print(f"pages processed: {processed}")
    print(f"pages changed: {changed}")
    print(f"lines joined: {joined}")
    print("remaining non-ASCII code points (top 25):")
    for ch, count in remaining.most_common(25):
        print(f"  U+{ord(ch):04X} {count}")


if __name__ == "__main__":
    main()
