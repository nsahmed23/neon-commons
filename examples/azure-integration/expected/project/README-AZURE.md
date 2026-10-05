# Synthetic Azure existing-backend integration

This fixture reuses, rather than provisions or adopts, an existing Azure storage backend. The storage account, container, network route, service principal/federated credential and permissions are **synthetic assumptions**, not discovered infrastructure. The policy component remains the only writer for the policy and its assignments.

`backend.tf` shows versioned OpenTofu azurerm backend fields. No state access is attempted. Verify all names/IDs and blob key against approved repository context; changing an existing backend key is a state migration, not harmless configuration cleanup. Do not turn on backend generation at the same time as this static backend block. The parent Atmos config has auto_generate_backend_file=false.

Bootstrap owner must supply a usable private network/DNS route, existing container and scoped data-plane identity before normal execution. Azure subscription RBAC, storage data-plane permission and Graph scopes are separate. Backend OIDC does not automatically configure the typed Intune provider. The provider's exact OIDC environment contract is still a qualification gap; never fall back to cached Azure CLI tokens.

CI examples intentionally perform offline checks and handoff only. They are not installed workflows. The live protected plan/import/change adapter is specified in recipes/azure-ci-identity.md but not implemented/validated. G08 therefore remains partial. No credentials are requested or output. Existing CI may reuse the contracts without adopting these templates.
