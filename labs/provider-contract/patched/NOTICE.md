This is a modified source candidate derived from Deployment Theory's
`internal/services/common/custom_requests/get_request.go` at commit
`1718c946b3ae111bb44c7c1d925b3e35b708cb0a` (microsoft365 provider 1.0.0).
The original copyright and MPL-2.0 license apply; LICENSE is included here.

Local changes add HTTP status and error rejection, exact collection origin/path
admission, continuation/size bounds, malformed and duplicate envelope rejection,
redirect rejection, and the missing initial query encoding. The unified patch,
original source and both hashes are supplied in this source distribution.

This candidate has not been submitted upstream, published, built as a provider
release or validated against Microsoft Graph. Its behavior is qualified only by
the specified in-memory source tests. Existing registry binaries remain unchanged.
