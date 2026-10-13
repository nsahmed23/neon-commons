"""Check SOURCE-REPLY-02 against the pins SOURCE-QUERY-02 sent and against itself.

Usage: py -3.11 -I tools/check_source_reply_02.py <inbox/SOURCE-REPLY-02.json> <outbox/SOURCE-QUERY-02.md>
Every pin below must appear verbatim in the sent query. Prints a sanitized verdict JSON: counts, statuses and
pins only; no evidence-tree paths beyond the two input roots, no attachment ids, no credential material.
"""
import json
import sys

ARCHIVES = {
    "r4-evidence": (1469518188, "7bbc9f88eee9b4c417f622fb76cb5e2c0b0d4790d5b7cceaa2ae661ce2012ad7",
                    35983862, "9f53658f8b795e136d32baab6d7043741a81cd6450e9d640489fb01a97610fb1"),
    "provider-candidates": (9849950, "755b9f4f8d29e562f476fc7e1f3bb8f376fd0fbfbeabe7a8e7e7ec78099280c7",
                            2875760, "bccf1c15dcda000ebeae37f1c23de016233d062d8a0edcf535b39f67ffd99fa6"),
    "current-diagnostic-scratch": (14485539, "60960f3760f24893e7114185d5d14ee7ab3e35e1fc17008097d2b6eecc83e939",
                                   5496, "43ef5e7852f9e2be9878cfc17ef096182d166fc693b970333828e54e11f7b992"),
    "current-exact-artifact-scratch": (41538870, "c221c1410d905806275dc3ea72c2793db83839816d112d4d3095e3bbe4819add",
                                       1677589, "5d8b84ecc1c8bf9690fa0cbfa0012650430e36f302f4982969a04366b7984c2e"),
}
RECEIPTS = {
    "r4-evidence": "21c10ba712bb77e39c4a998928e32eab7f1d1a51cc7ce7d8394d63aaa3fe0aee",
    "provider-candidates": "e6d56171467b72f1f3c7f236da43c9a4b83170895af9faa272c06ec9cc022f84",
    "current-diagnostic-scratch": "31e08a8fbc3fbd123e8ec9b3b16ebf879c2ef56832031146767b9f10e0e5f243",
    "current-exact-artifact-scratch": "a1c2c1fcabdcb01df48d17e099656bad10571f6e5434871cfa578609a7559b02",
}
PREFIX_TYPES = {"ghp": "CLASSIC_PAT", "gho": "OAUTH_APP", "ghu": "APP_USER", "ghs": "APP_INSTALLATION", "github": "FINE_GRAINED_PAT"}


def main():
    reply = json.load(open(sys.argv[1], encoding="utf-8"))
    query = open(sys.argv[2], encoding="utf-8").read()
    for label, (size, sha, msize, msha) in ARCHIVES.items():
        for pin in (sha, msha, RECEIPTS[label], str(size), str(msize)):
            assert pin in query, f"pin {pin[:12]} for {label} not in the sent query"
    pin_hashes = {v[1] for v in ARCHIVES.values()} | {v[3] for v in ARCHIVES.values()}
    pin_sizes = {v[0] for v in ARCHIVES.values()} | {v[2] for v in ARCHIVES.values()}

    runtime = reply["runtime"]
    copies = reply["copies"]
    hits = copies["hits"]
    receipts = {row["label"]: row for row in reply["receipts"]["rows"]}
    receipt_rows = []
    for label, row in receipts.items():
        size, sha, msize, msha = ARCHIVES[label]
        scal = row["recorded_scalar_fields"]
        receipt_rows.append({
            "label": label, "receipt_sha256_matches_pin": row["sha256"] == RECEIPTS[label],
            "recorded_archive_matches_c32_pin": scal["bytes"] == size and scal["sha256"] == sha,
            "recorded_manifest_sha256_matches_pin": scal["manifest_sha256"] == msha,
            "input_root": scal["input_epoch"], "regular_files": scal["regular_files"], "regular_bytes": scal["regular_bytes"],
            "directories": scal["directories"], "literal_symlinks": scal["literal_symlinks"],
            "explicit_ipc_omissions": row["list_lengths"].get("explicit_ipc_omissions"),
        })
    census_rows = []
    for root in reply["census"]["roots"]:
        label = "r4-evidence" if root["path"].endswith("epoch-20261007-r4") else "provider-candidates"
        scal = receipts[label]["recorded_scalar_fields"]
        pre, now = root["at_or_before_cutoff"], root["all_entries"]
        census_rows.append({
            "label": label, "root": root["path"],
            "regular_files_match_receipt": pre["regular"] == scal["regular_files"],
            "regular_bytes_match_receipt": pre["regular_bytes"] == scal["regular_bytes"],
            "symlinks_match_receipt": pre["symlink"] == scal["literal_symlinks"],
            "fifo_count_equals_omission_list_length": pre["FIFO"] == receipts[label]["list_lengths"].get("explicit_ipc_omissions"),
            "directories_at_or_before_cutoff_minus_receipt": pre["directory"] - scal["directories"],
            "directories_now": now["directory"],
            "regular_files_added_after_cutoff": now["regular"] - pre["regular"],
            "regular_bytes_added_after_cutoff": now["regular_bytes"] - pre["regular_bytes"],
            "largest_regular_bytes": now["largest_regular_bytes"],
            "regular_over_100MiB": now["regular_over_104857600"], "regular_over_2GiB": now["regular_over_2147483648"],
            "structural_sha256_at_or_before_cutoff": root["structural_sha256_at_or_before_cutoff"],
        })
    post = reply["post_cutoff_records"]
    gh = reply["github_client"]
    prefix = gh["d"]["output"].split()[-1] if gh["d"]["output"].strip() else None
    out = {
        "runtime": {"kernel_boot_utc": runtime["kernel_boot_utc"], "restart_since_reply_01": runtime["boot_differs_from_20261013T155205Z"],
                    "source_head_is_c32_baseline": runtime["observed_source_HEAD"] == runtime["immutable_C32_baseline"] == "d057cc15c9928dd1a34a965b8d8ebf8e6755d94a"},
        "copies": {"roots_covered": copies["roots_covered"], "roots_not_covered": [r["path"] for r in copies["roots_not_fully_covered"]],
                   "hits": len(hits), "hit_names": sorted({h["path"].rsplit("/", 1)[-1] for h in hits}),
                   "hit_bytes": sorted(h["bytes"] for h in hits),
                   "any_hit_matches_a_pin": any(h["sha256"] in pin_hashes for h in hits),
                   "any_hit_has_a_pinned_size": any(h["bytes"] in pin_sizes for h in hits),
                   "verdict": "NO_SURVIVING_COPY_IN_SEARCHED_ROOTS"},
        "receipts": receipt_rows,
        "census": census_rows,
        "post_cutoff_records": {"newly_listed": len(post["records"]), "total": post["total_count_in_prior_query_scope"],
                                "complete": post["list_complete"],
                                "epoch_count_agrees_with_census": post["epoch_total_count"] == census_rows[0]["regular_files_added_after_cutoff"]},
        "github_client": {"gh_version": gh["a"]["output"], "release_upload_subcommand": gh["b"]["output"].splitlines()[0].endswith(" 0"),
                          "api_subcommand": gh["b"]["output"].splitlines()[1].endswith(" 0"),
                          "token_prefix_type": PREFIX_TYPES.get(prefix, "UNKNOWN"), "reported_auth_type": gh["auth_type"],
                          "oauth_scopes": gh["h"]["X-OAuth-Scopes"], "client_id_header_present": gh["h"]["X-OAuth-Client-Id_present"],
                          "token_expiration_header_present": gh["h"]["github-authentication-token-expiration_present"],
                          "proxy_variables_set": "HTTPS_PROXY SET" in gh["c"]["output"],
                          "extraheader": gh["f"]["interpretation"], "credential_helper": gh["g"]["interpretation"],
                          "user_status": gh["h"]["HTTP_status"], "login": gh["h"]["body"]["login"]},
        "errors": [f'{e["step"]}: {e["code"]}' for e in reply["errors"]],
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
