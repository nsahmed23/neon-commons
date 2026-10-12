# Linux CI fixture-binding preparation — not deployed

This prepared layer supplies the missing explicit validation fixture contract. It installs or runs no binary, downloads nothing, changes no daemon/image and grants no protected worker authority. Exact Docker28.4.0/OpenTofu1.13.1/relayv2/v3 pins come from existing `scripts/qualification_tools.py` without caller repinning. The runner/fixture custodian must provide approved existing files. The supplied workflow is an unactivated source proposal; current stockUbuntu paths and workflow registration remain external prerequisites.

Place the reviewed new script beside the existing `qualification_tools.py` and `prepare-qualification-tools.py`, preserving their exact bytes. Its intrinsic closed contract accepts allfour explicit localtool paths; the profile JSON describes this contract and is not an approval artifact. Actual checked inputs produce five environment entries, including `INTUNE_TEST_TOFU_EXECUTABLE`, so the two completion methods no longer require creating an ambiguous historical `/tmp`alias. The historical default remains only for originalreplays; skips remain release failures.

Actual inspected CLI:

```sh
python -B scripts/prepare-ci-qualification.py bind --docker EXACT_DOCKER --tofu EXACT_TOFU --relay-v2 EXACT_RELAY_V2 --relay-v3 EXACT_RELAY_V3 --output NEW_PRIVATE_INPUT_DIRECTORY
python -B scripts/prepare-ci-qualification.py export --input NEW_PRIVATE_INPUT_DIRECTORY
```

The proposed workflow uses already supplied repository variables solely as literal path arguments and appends the rechecked path-only output to its existing `$GITHUB_ENV`. Setting those variables, preparing runner files or dispatching/registering the workflow is not authorized by this source layer. The current Ubuntu validator and every source/extracted verifier gate retain zero-skip/zero-failure requirements. No contents permission, action pin, trigger, Linux/Python image declaration or production workflow is changed.

Author qualification:29local controls, actualbind/exportCLI and two edited native localOpenTofu methods pass, zero skips. Alloriginalbinary/toolbytes remain exact, including a post-native closure. Pure controls are not added to test totals; methods overlap current2326/e3history. No new fullsuite/CI/provider/tenant/device/nativeWindows/AppSec/productionPASS. Negative controls preserve wrong/missing/type/control paths, malformed/duplicateexportkeys, wrongbinary, aliases, symlink/FIFO and existingoutput. Native method intermediate TemporaryDirectories retain existingcleanup and are explicitly not a complete raw recovery capsule. Independent exactsource/publicselection review remains required before branchpublication.
