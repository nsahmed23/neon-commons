// Local MPL-2.0 provider repair candidate. See completion/NOTICE.md.
package customrequests

import (
	"context"
	"encoding/json"
	"fmt"
	settingsjson "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/settingsjson"
	abs "github.com/microsoft/kiota-abstractions-go"
	ser "github.com/microsoft/kiota-abstractions-go/serialization"
	kiotahttp "github.com/microsoft/kiota-http-go"
	"io"
	"net/http"
	"net/url"
	"time"
)

type boundedRawResponse struct{ body []byte }

func (*boundedRawResponse) GetFieldDeserializers() map[string]func(ser.ParseNode) error { return nil }
func (*boundedRawResponse) Serialize(ser.SerializationWriter) error {
	return fmt.Errorf("response cannot be serialized")
}

// Use the configured adapter for authentication, retry and transport. This path
// never invokes the legacy makeRequest shared by DELETE. Public Graph beta is the
// only admitted deployment profile; sovereign endpoints need separate evidence.
func GetConfigurationPolicyCollection(ctx context.Context, adapter abs.RequestAdapter, cfg GetRequestConfig) (json.RawMessage, error) {
	if cfg.Endpoint != "/deviceManagement/configurationPolicies" || (cfg.EndpointSuffix != "/settings" && cfg.EndpointSuffix != "/assignments") {
		return nil, fmt.Errorf("unsupported collection profile")
	}
	if cfg.APIVersion != GraphAPIBeta {
		return nil, fmt.Errorf("unsupported settings API version")
	}
	rootInfo := abs.NewRequestInformation()
	rootInfo.UrlTemplate = ByIDRequestUrlTemplate(cfg)
	rootInfo.PathParameters = map[string]string{"baseurl": "https://graph.microsoft.com/beta"}
	root, e := rootInfo.GetUri()
	if e != nil || root.Scheme != "https" || root.Host != "graph.microsoft.com" || root.User != nil || root.Fragment != "" {
		return nil, fmt.Errorf("invalid collection URL")
	}
	if base := adapter.GetBaseUrl(); base != "" && base != "https://graph.microsoft.com/beta" {
		return nil, fmt.Errorf("configured adapter Graph profile differs")
	}
	query := root.Query()
	for k, v := range cfg.QueryParameters {
		query.Set(k, v)
	}
	root.RawQuery = query.Encode()
	current := root
	seenLinks := map[string]bool{}
	seenIDs := map[string]bool{}
	items := make([]any, 0)
	total := 0
	expectedCount := -1
	for page := 0; page < 128; page++ {
		if seenLinks[current.String()] {
			return nil, fmt.Errorf("collection continuation loop")
		}
		seenLinks[current.String()] = true
		info := abs.NewRequestInformation()
		info.Method = abs.GET
		info.SetUri(*current)
		info.Headers.Add("Accept", "application/json")
		info.AddRequestOptions([]abs.RequestOption{&kiotahttp.RedirectHandlerOptions{ShouldRedirect: func(*http.Request, *http.Response) bool { return false }}})
		option := abs.NewRequestHandlerOption()
		option.SetResponseHandler(func(response interface{}, _ abs.ErrorMappings) (interface{}, error) {
			r, ok := response.(*http.Response)
			if !ok || r == nil || r.Body == nil {
				return nil, fmt.Errorf("adapter returned no HTTP response")
			}
			defer r.Body.Close()
			if r.StatusCode != http.StatusOK {
				return nil, fmt.Errorf("collection HTTP status %d", r.StatusCode)
			}
			if r.Request != nil && r.Request.URL.String() != current.String() {
				return nil, fmt.Errorf("unexpected collection response URL")
			}
			b, e := io.ReadAll(io.LimitReader(r.Body, 4*1024*1024+1))
			if e != nil || len(b) > 4*1024*1024 {
				return nil, fmt.Errorf("collection body unavailable or oversized")
			}
			return &boundedRawResponse{body: b}, nil
		})
		pageCtx, cancel := context.WithTimeout(context.WithValue(ctx, abs.ResponseHandlerOptionKey, option), 30*time.Second)
		response, e := adapter.Send(pageCtx, info, nil, nil)
		cancel()
		if e != nil {
			return nil, fmt.Errorf("collection request failed")
		}
		raw, ok := response.(*boundedRawResponse)
		if !ok {
			return nil, fmt.Errorf("adapter did not honor bounded response handler")
		}
		total += len(raw.body)
		if total > 32*1024*1024 {
			return nil, fmt.Errorf("collection total byte limit exceeded")
		}
		value, e := settingsjson.Decode(raw.body)
		if e != nil {
			return nil, e
		}
		object, ok := value.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("collection response must be an object")
		}
		if _, bad := object["error"]; bad {
			return nil, fmt.Errorf("collection error envelope")
		}
		rows, ok := object["value"].([]any)
		if !ok {
			return nil, fmt.Errorf("collection value must be an array")
		}
		if count, present := object["@odata.count"]; present {
			n, ok := count.(json.Number)
			if !ok {
				return nil, fmt.Errorf("invalid collection count")
			}
			num, e := n.Int64()
			if e != nil || num < 0 || num > 10000 {
				return nil, fmt.Errorf("invalid collection count")
			}
			if expectedCount >= 0 && int(num) != expectedCount {
				return nil, fmt.Errorf("collection count changed")
			}
			expectedCount = int(num)
		}
		for _, v := range rows {
			row, ok := v.(map[string]any)
			if !ok {
				return nil, fmt.Errorf("collection item must be object")
			}
			id, ok := row["id"].(string)
			if !ok || id == "" || seenIDs[id] {
				return nil, fmt.Errorf("collection identity missing or duplicated")
			}
			seenIDs[id] = true
			items = append(items, v)
		}
		if len(items) > 10000 {
			return nil, fmt.Errorf("collection item limit exceeded")
		}
		next, more := object["@odata.nextLink"]
		if !more {
			if expectedCount >= 0 && len(items) != expectedCount {
				return nil, fmt.Errorf("collection count mismatch")
			}
			return json.Marshal(map[string]any{"value": items})
		}
		link, ok := next.(string)
		if !ok || link == "" {
			return nil, fmt.Errorf("invalid continuation")
		}
		parsed, e := url.Parse(link)
		if e != nil || parsed.Scheme != root.Scheme || parsed.Host != root.Host || parsed.User != nil || parsed.Fragment != "" || parsed.EscapedPath() != root.EscapedPath() {
			return nil, fmt.Errorf("continuation outside admitted collection")
		}
		current = parsed
	}
	return nil, fmt.Errorf("collection page limit exceeded")
}
