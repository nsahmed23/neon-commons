# Primary-source basis

Reviewed 2026-10-04. These are service contract references, not evidence of a successful live call.

| Microsoft source | Implementation decision |
| --- | --- |
| [Access tokens](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens) | Clients treat Microsoft access tokens as opaque and use response metadata for expiry. No JWT decoding, token introspection site, or local Graph access-token validation. |
| [OAuth client credentials](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow) | Explicit tenant-specific v2 token POST, URL-encoded secret, client ID, single resource `.default` scope and `client_credentials` grant. |
| [Get servicePrincipal](https://learn.microsoft.com/en-us/graph/api/serviceprincipal-get?view=graph-rest-1.0) | Address the object by `appId`, select only required properties. A service principal can retrieve its own details without application permissions; identity discovery need not request a directory-wide grant. |
| [Subscriptions Get, 2022-12-01](https://learn.microsoft.com/en-us/rest/api/resources/subscriptions/get?view=rest-resources-2022-12-01) | Fixed subscription GET and comparison of `subscriptionId`, `tenantId`, and enabled state. |
| [Storage Accounts Get Properties, 2023-05-01](https://learn.microsoft.com/ga-ie/rest/api/storagerp/storage-accounts/get-properties?view=rest-storagerp-2023-05-01) | Fixed storage resource GET and `properties.primaryEndpoints.blob` comparison. The English endpoint returned an internal retrieval error; the official localized page exposes the same API version and contract. |
| [Get Blob](https://learn.microsoft.com/en-us/rest/api/storageservices/get-blob) | Read exact existing state bytes with OAuth authorization and bounded response collection. |
| [Conditional Blob headers](https://learn.microsoft.com/en-us/rest/api/storageservices/specifying-conditional-headers-for-blob-service-operations) | `If-Match` is supported by Get Blob and Get Blob Properties. Failed conditions return 412. |

The authentication conclusion is an implementation inference from a successful fixed tenant-specific exchange and matching self-principal response, with ARM and Blob observations added for the backend. The module never derives tenant or client identity by decoding a Microsoft access token. Resource reads and authentication are distinct from permissions to mutate Intune or hold backend writer ownership.
