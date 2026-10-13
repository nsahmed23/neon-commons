"""Check SOURCE-REPLY-01 against the pins that SOURCE-QUERY-01 sent.

Usage: py -3.11 -I tools/check_source_reply.py <inbox/SOURCE-REPLY-01.json> <outbox/SOURCE-QUERY-01.md>
Every pin below must appear verbatim in the sent query (so this script cannot drift from it).
Prints a sanitized verdict JSON: no environment ids, Drive ids, process lists or credentials.
"""
import json
import sys

PINS = {
    "archive:r4-evidence": (1469518188, "7bbc9f88eee9b4c417f622fb76cb5e2c0b0d4790d5b7cceaa2ae661ce2012ad7"),
    "archive:provider-candidates": (9849950, "755b9f4f8d29e562f476fc7e1f3bb8f376fd0fbfbeabe7a8e7e7ec78099280c7"),
    "archive:current-diagnostic-scratch": (14485539, "60960f3760f24893e7114185d5d14ee7ab3e35e1fc17008097d2b6eecc83e939"),
    "archive:current-exact-artifact-scratch": (41538870, "c221c1410d905806275dc3ea72c2793db83839816d112d4d3095e3bbe4819add"),
    "probe:zip": (18445, "d01a9b0e9cd1506b1ee5d0defcfebf4f377af858ab610d3ec5362623ee0c67c3"),
}


def fmt(n):
    return f"{n:,}"


def main():
    reply = json.load(open(sys.argv[1], encoding="utf-8"))
    query = open(sys.argv[2], encoding="utf-8").read()
    for key, (size, sha) in PINS.items():
        assert sha in query, f"pin hash for {key} not in the sent query"
        assert fmt(size) in query or str(size) in query, f"pin size for {key} not in the sent query"
    rows = []
    for item in reply["archives"]:
        size, sha = PINS["archive:" + item["label"]]
        rows.append({
            "object": item["label"],
            "echoed_pin_matches_sent_pin": item["expected_bytes"] == size and item["expected_sha256"] == sha,
            "availability": item["availability"],
            "error": item.get("error_code"),
            "fresh_sha256": item["fresh_sha256"],
            "verdict": "PIN-MATCH" if item["fresh_sha256"] == sha else "ABSENT" if item.get("error_code") == "ENOENT" else "MISMATCH",
        })
    probe = reply["probe"]["zip"]
    size, sha = PINS["probe:zip"]
    rows.append({
        "object": "synthetic-original-work-probe.zip",
        "echoed_pin_matches_sent_pin": probe["expected_bytes"] == size and probe["expected_sha256"] == sha,
        "availability": "PRESENT",
        "fresh_bytes": probe["bytes"],
        "fresh_sha256": probe["fresh_sha256"],
        "size_mtime_unchanged": probe["size_mtime_unchanged"],
        "verdict": "PIN-MATCH" if probe["bytes"] == size and probe["fresh_sha256"] == sha else "MISMATCH",
    })
    receipt = reply["probe"]["receipt"]
    rows.append({"object": "WORK-EXPORT-PROBE.json", "fresh_bytes": receipt["bytes"],
                 "verdict": "PIN-MATCH (pin from the Work task's own receipt)" if receipt["pin_match"] else "MISMATCH"})
    env = reply["environment"]
    roots = {r["label"]: r["currently_exists"] for r in reply["archive_format"]["layer_input_roots"]}
    cap = reply["capacity"]
    gh = reply["github_mechanism"]
    out = {
        "reply_sha256_local": "see inbox/RECEIVED-01.json",
        "runtime": {"new_runtime_start": env["reset_or_resumption"]["result"], "kernel_boot_utc": env["kernel_boot_time_utc"],
                    "cause": env["reset_or_resumption"]["cause"], "source_head": env["local_HEAD"],
                    "files_created_or_modified_by_query": env["files_created_or_modified_by_query_commands"]},
        "objects": rows,
        "layer_input_roots_exist": roots,
        "capacity_bytes": {"workspace_account_available": cap["/workspace"]["account_available_bytes"],
                           "workspace_filesystem_free": cap["/workspace"]["filesystem_free_bytes"],
                           "tmp_available": cap["/tmp"]["available_bytes"],
                           "cgroup_memory_limit": cap["memory"]["cgroup_memory_limit_bytes"]},
        "github": {"c32_method": "native git CLI push", "clients_present": sorted(gh["command_v"]),
                   "gh_api_user_status": gh["gh_api_user"]["http_status"], "oauth_scopes": gh["gh_api_user"]["X-OAuth-Scopes"],
                   "credential_helper": gh["git_config_credential_helper"]["helper_name"],
                   "private_repo_access": gh["private_repository_owned_by_nsahmed23_access"],
                   "release_asset_upload_permission": gh["release_asset_upload_permission"]},
        "drive": {"retried_by_query": reply["drive_action"]["action_invoked_or_retried_by_this_query"],
                  "historical": f'{reply["drive_action"]["http_status"]} {reply["drive_action"]["error_reason"]}'},
        "post_cutoff_records": {"listed": reply["post_cutoff_records"]["listed_count"],
                                "total": reply["post_cutoff_records"]["total_count"],
                                "complete": reply["post_cutoff_records"]["list_complete"]},
        "errors": [f'{e["step"]}: {e["error_code"]}' for e in reply["errors"]],
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
