# Optional CLM advisory judge

`intune_iac.judge.assess(config_path, claim, evidence)` sends a real HTTP request to an explicitly configured CLM service. `claim` is a nonempty literal string; `evidence` is a nonempty JSON object or array. Include source IDs, tenant/policy scope and coverage in the evidence bundle when they matter. The caller is responsible for establishing their provenance and completeness.

```sh
python -m intune_iac judge --config examples/clm-config.json \
  --claim 'The selected policy preserves its supplied setting value.' \
  --evidence evidence.json
```

The CLI reads `evidence.json`; the Python API accepts its decoded value. Nothing in this adapter downloads weights, installs packages, starts a server, invokes model code or dispatches actions. The HTTP service must already exist. Every result contains `advisory_only: true` and `execution_authorized: false`. Deterministic preservation, scope and action checks remain independent.

## Configure an existing local deployment

Copy [the configuration template](../examples/clm-config.json) and replace its `REPLACE_...` values, `logit_scale: null`, artifact paths and serving settings with the actual deployment identity. The template intentionally fails closed until populated. Pins are lowercase hexadecimal: source/encoder commit 40–64 characters, artifact SHA256 exactly 64 characters. `projection` should record the full checkpoint `cfg` and effective projection dimension; `logit_scale` is the effective positive multiplier `min(exp(checkpoint_logit_scale), 100)`, not its logarithm. Do not deserialize an untrusted checkpoint to obtain metadata; use the trusted release record. Record the effective dtype and quantization.

Use an existing, trusted, immutable head file and the tokenizer JSON from the pinned encoder release. Relative artifact paths resolve against the configuration directory. A local `head_path` is optional for a remote deployment; when supplied, its bytes must match `head_sha256` both before and after the HTTP request. The tokenizer file is always required for the token safety gate. Obtain hashes with `sha256sum` or equivalent. The adapter never imports Torch or a tokenizer runtime.

The checked CLM source at `bb42c6c5bf914fd449bed2f6ca65be80602cb1f7` supports this serving shape. For an already provisioned CLM environment, the corresponding local service configuration is:

```sh
clm-serve --host 127.0.0.1 --port 8700 --no-download --no-ui \
  --model intune-evidence=/srv/clm/heads/immutable.pt \
  --emb-url http://127.0.0.1:8090/v1/embeddings \
  --emb-model qwen3-8b --max-tokens 2048
```

The encoder must be the pinned Qwen3-8B release with 4096-wide last-token pooling. Its effective input limit must match the configured `encoder_max_tokens`. Its request recipe must tokenize raw text without a chat template or extra special-token wrapper. The current CLM launcher does not pin encoder revision or establish effective pooling by itself; qualify the encoder deployment separately. Keep serving generations immutable and restart/clear CLM caches when identity changes. CLM hot reload does not report checkpoint digests and may mix generations during concurrent reload.

`configured_model_identity` records expected release metadata. `observed_model_identity` records only the returned alias and explicitly states that weights and encoder/head identity are unauthenticated. A matching alias or local checkpoint digest cannot prove the remote process used those weights. No CLM response currently supplies that attestation. The adapter does not turn operator configuration into observed inference identity.

Only numeric loopback HTTP destinations and `localhost` are allowed without additional configuration. `localhost` is converted to `127.0.0.1`. A remote endpoint must be HTTPS and set `allow_remote_https: true`; TLS certificate verification is enabled. The path must be exactly `/v1/systemone`, without query, fragment or URL credentials. Redirects and environment proxies are disabled, so bearer credentials are sent only to the explicitly configured destination.

For optional server authentication, add `"api_key_env": "CLM_API_KEY"` and set that environment variable to the service bearer key. Only names starting with `CLM_` are accepted. Keys never appear in returned receipts. A configured missing key is an unavailable assessment. CLM's shared bearer key is not tenant identity or execution permission.

## Token safety and evidence binding

The adapter uses the actual System One protocol from `src/clm/server.py`, `schema.py` and `engine.py`: `POST /v1/systemone` with a string `state`, model alias, inference temperature, and a single `choice` question keyed `evidence_assessment`. The three labels and their complete descriptions are fixed, ordered `supported`, `contradicted`, `insufficient`. They cannot be replaced through configuration.

The string state is canonical JSON containing the exact claim and evidence bundle. CLM appends the question instructions after two newlines. `rendered_state_sha256` hashes this exact complete encoder text. `evidence_sha256`, `claim_sha256`, `candidate_set_sha256`, `model_config_sha256` and `request_sha256` separately bind the supplied bundle, claim, candidate descriptions/order, expected model configuration and request. These are wrapper provenance, not model-selected citations. No rationale or citations are invented.

The supported method, `qwen3_byte_bpe_upper_bound_v1`, inspects the pinned local tokenizer JSON. It accepts byte-level BPE with no normalizer, no added-prefix space, no byte fallback, no subword prefix/suffix, and no token-adding postprocessor. A leading isolating Split and a ByteLevel postprocessor are supported. Each UTF-8 byte contributes at most one initial symbol; BPE merges and added-token matching can only reduce the count. Thus the UTF-8 byte count safely bounds each raw-text token sequence for this recipe. This is conservative: it may reject evidence that an exact tokenizer could fit.

Each complete state-plus-question and each complete candidate must fit **both** configured encoder and CLM limits. Unknown encoders, altered tokenizer hashes, unsupported tokenizer transformations, missing files or overflowing bounds abstain before HTTP. No evidence clipping, implicit chunking or fallback counter occurs. The service's configured raw-text recipe and limits are deployment assumptions, explicitly recorded in the receipt; the CLM protocol cannot observe hidden server-side changes. A deployment using templates or extra tokens needs a separately qualified counter and is unsupported here.

Claim bytes are capped at 4 KiB, evidence at 64 KiB, 8,192 JSON values and depth 32, configuration and response at 64 KiB, and tokenizer JSON at 32 MiB. Non-JSON Python values and nonfinite numbers are rejected. Socket timeout is configurable from 0.05 to 60 seconds; default 10.

## Interpreting the result

| Field | Meaning |
|---|---|
| `status: assessed` | A supported or contradicted candidate passed the configured selection gate; still advisory. |
| `status: abstained` | Insufficient evidence won, a tie occurred, or probability/margin failed the gate. |
| `status: unavailable` | Configuration, token safety, service availability or response validation failed. |
| `verdict` | Always one of the three fixed labels; every error returns `insufficient`. |
| `probabilities` | Complete candidate-relative softmax distribution, retained only for a validated response. |
| `candidate_relative_confidence` | CLM's top probability minus the mean of the other probabilities. |
| `top_two_margin` | Difference between the largest and second-largest probabilities. |
| `reason_code` | Fixed safe error or selection code, without server-body or exception-text leakage. |

Responses must have the expected alias, exact question ID, all and only the three finite probabilities in `[0,1]`, sum within `1e-6` of 1, a maximizing label, and finite consistent confidence. Probabilities are validated, never silently renormalized. Ties always abstain, including CLM's first-candidate tie behavior. HTTP errors, timeouts, unavailable services, oversized or malformed JSON and duplicate JSON keys never imply support. `/health` is not used as readiness proof: the checked CLM implementation can return `ok: true` when the encoder is unavailable.

The example thresholds `0.8` probability and `0.2` margin are policy gates, **not measured calibration**. Neither confidence nor these thresholds establishes factual correctness. All thresholds and rubric/identity variants need held-out task evaluation before any production reliance. No learned-model quality, performance or encoder readiness was established during this implementation.

Run `python -m unittest plugin_tests.test_judge -v` from the plugin root. Tests send real serialized HTTP to a loopback stdlib server with synthetic response distributions. They check protocol, binding, credential containment, redirects, timeouts, malformed distributions and preflight rejection; they do not run model inference.
