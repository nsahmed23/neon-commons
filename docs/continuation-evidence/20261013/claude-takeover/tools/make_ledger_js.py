"""Regenerate board/ledger.js and board/ledger.json from ledger/ledger.json.

The board loads ledger.js with a plain <script> tag, because browsers block
fetch() of a local JSON file opened from file://. Run after every ledger edit:

    py -3.11 -I tools/make_ledger_js.py C:/Dev/Projects/intune-rescue
"""
import json
import pathlib
import sys

REQUIRED_KEYS = {
    "schema", "updated_utc", "outcome_flags", "owner_asks", "lanes",
    "milestones", "source_transfer", "gates", "observations", "events",
}


def main(root: str) -> None:
    base = pathlib.Path(root)
    ledger = json.loads((base / "ledger" / "ledger.json").read_text(encoding="utf-8"))
    missing = REQUIRED_KEYS - ledger.keys()
    if missing:
        raise SystemExit(f"ledger.json is missing keys: {sorted(missing)}")
    text = json.dumps(ledger, indent=2, ensure_ascii=False)
    board = base / "board"
    (board / "ledger.json").write_text(text + "\n", encoding="utf-8", newline="\n")
    (board / "ledger.js").write_text(
        "// Generated from ledger/ledger.json by tools/make_ledger_js.py. Do not edit.\n"
        f"window.LEDGER = {text};\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"ok: {len(ledger['lanes'])} lanes, {len(ledger['milestones'])} milestones, "
          f"{len(ledger['source_transfer'])} transfer rows, updated {ledger['updated_utc']}")


if __name__ == "__main__":
    main(sys.argv[1])
