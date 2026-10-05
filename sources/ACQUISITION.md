# Acquisition and dependency closure

This pack contains original reference code and original synthetic fixtures. It does **not** vendor upstream implementations. `source-lock.json` pins selected sources; `code-catalog.jsonl` distinguishes connector-reviewed text from acquired raw bytes. GitHub returned blob IDs, but local raw-source SHA-256 values remain null. A rendered connector response is not the original archive.

Container HTTPS acquisition failed (name-resolution failure); a separate archive-download attempt was unavailable. Public repository inspection through the GitHub connector succeeded. Thus this is a pinned retrieval map plus source review, **not a complete acquired dependency closure**. G09 remains partial. The original generated-file hashes and ZIP hashes are independently calculated from actual local bytes.

Future acquisition in an approved environment: use `tools/acquire-selected.py --allow-network --output <new-empty-directory>` after reviewing it. It obtains only selected immutable raw GitHub files with known blob IDs and verifies their Git blob SHA-1 before writing; it creates its own SHA-256 receipt. It neither installs nor executes those sources. Reject redirects outside raw.githubusercontent.com. Licenses and transitive files must also be acquired and reviewed before copying implementation into a distributed plugin. Current catalogue records identify unresolved dependencies rather than claiming closure.

Do not download whole repositories into the runtime. Keep source material separate from runtime and hidden assessment fixtures. Re-evaluate all branches/tags, licenses and host specs as a versioned update, not an automatic upgrade. Any new provider pin invalidates mapping and generation qualifications.
