# Relocatable exact qualification tools

The strict source verifier discovers actual Docker host and protected service
tests. These require their real native prerequisites; absence remains an error,
never a skip. Historical test defaults still identify the previously qualified
workspace paths. Explicit inputs now permit the same pinned bytes at a different
absolute path, including an extracted-source or separately prepared CI workspace.

| Environment input | Required identity |
| --- | --- |
| `INTUNE_QUALIFICATION_DOCKER` | Docker client28.4.0, SHA-256 `27f239f97492c434e091a70b41b8796c698f0aa2b6052c6f9c28da4ee7ae888b` |
| `INTUNE_QUALIFICATION_TOFU` | OpenTofu1.13.1, SHA-256 `a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a` |
| `INTUNE_QUALIFICATION_RELAY_V2` | Historical repaired relay-v2, SHA-256 `2e321b0efa62fcd710401b814a18b8afd3140ea0202fd1b516875bd814564697` |
| `INTUNE_QUALIFICATION_RELAY_V3` | Current relay-v3, SHA-256 `4255592e3b477d9c7fba06a59536d07effaa2a54e9e848f4908fecae672a25a0` |

`scripts/qualification_tools.py` binds these versions to their retained exact
size/digest records. It rejects changed bytes, links, unsafe ancestors, writable
executables, missing explicit paths and unknown roles. Environment variables can
choose paths, not hashes or versions. A failed override cannot fall back to the
old path. The ordinary worker host independently rechecks the fixed Docker and
declared tool pins when dispatching; test PinnedTool expectations use the fixed
role digest, never a new digest of a potentially replaced path. This helper
grants no execution authority. Path validation assumes a cooperative trusted
user: held parent/name identity is revalidated, but the complete parent namespace
is not held immovable. No hostile same-user namespace isolation is claimed.

Prepare a new private reference receipt from already available approved tools:

```text
python -B scripts/prepare-qualification-tools.py verify --docker EXACT_DOCKER --tofu EXACT_TOFU --relay-v2 EXACT_RELAY_V2 --relay-v3 EXACT_RELAY_V3 --output NEW_INPUT_RECEIPT_DIRECTORY
```

The command reads bytes only. `environment.json` contains exactly the four path
inputs and `receipt.json` records fixed versions, hashes and limitations. Export
those exact reviewed path values in the verifier process environment; do not
execute the JSON as shell code. Every consumer hashes its input again. Actual
native Docker/OpenTofu version execution stays in the existing host tests.

On the retained qualified Debian GCC14.2 static toolchain, both exact relay
artifacts can be rebuilt without downloads:

```text
python -B scripts/prepare-qualification-tools.py build-relays --compiler /usr/bin/x86_64-linux-gnu-gcc-14 --relay-v2-source /ABS/FINAL_SOURCE/native/worker-relay/relay-v2.c --relay-v3-source /ABS/FINAL_SOURCE/native/worker-relay/relay.c --output NEW_PRIVATE_BUILD_ROOT
```

Pass absolute source paths. The helper requires the reviewed source/compiler/
linker/static-library pins, uses fixed arguments and an isolated environment,
and accepts only the already qualified output sizes and hashes. Each source is
materialized unchanged under its historical `relay.c` basename because the ELF
file symbol affects reproducibility. The first wrong-basename attempt and its
rejected binary remain preserved. Incompatible compiler/library output is a
blocked build, not an invitation to repin. The result is byte reproduction only;
no relay or container is launched by this command. Input receipts and failed
partial outputs are never replaced or removed automatically.

The complete native prerequisites remain separate: Linux x86_64, an already
authorized Docker28.4.0 daemon and its pinned existing Alpine image, the admitted
nonroot UID/GID profile, seccomp/network-none boundary, static OpenSSL/zlib/zstd
probe build dependencies, and the separately prepared signature validator. The
current host tests use UID/GID1000. Generic hosted Ubuntu runners are not presumed
to meet that profile. This preparation does not install Docker, change daemon
permissions, pull images, grant capabilities, provision credentials, or claim a
hosted CI run passed. An approved matching environment or a separately qualified
host-profile change is required before that gate can pass.

Run the unchanged strict verifier against the exact extracted source with the
four reviewed inputs and the existing validator input. Preserve its complete
result, actual native effects and exact package/tool identities. Local relocation
checks and source-byte reproduction do not substitute for final-package, native
Windows, live service/device, AppSec or accountable organizational approval.
