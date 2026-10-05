# Permission model

See permission-matrix.csv for per-operation distinctions. Read scopes listed in source are not evidence a particular principal is constrained to a policy cohort. Azure roles, Entra directory roles, Graph OAuth permissions and Intune service scoping are separate. An app-only principal needs independently qualified scope behavior. A portal role or scope tag is not enough to infer that boundary.

Keep discovery, mutation, assignment and high-impact device actions separately owned where possible. Never request admin consent, self-grant roles, switch tenant/subscription, or use cached privileged credentials during offline work. Negative authorization tests happen only in an approved disposable scope; target IDs and baseline must be controlled so a denial is interpretable. A denied inventory request stays incomplete, not empty.

This file is a research contract, not security approval. Live operations remain blocked pending organization identity, provider API and environment qualification.
