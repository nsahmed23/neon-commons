package contract

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"testing"

	custom "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/custom_requests"
)

const admitted = "https://graph.microsoft.com/beta/deviceManagement/configurationPolicies('11111111-1111-1111-1111-111111111111')/settings"

func pageBody(link string) string {
	v := map[string]any{"value": []any{map[string]any{"id": "0"}}}
	if link != "" {
		v["@odata.nextLink"] = link
	}
	b, _ := json.Marshal(v)
	return string(b)
}
func TestPatchFirstHTTP403Rejected(t *testing.T) {
	b, _, e := fetch(t, []page{{403, `{"error":{"code":"AccessDenied","secret":"restricted"}}`, nil}})
	if e == nil || b != "" || strings.Contains(e.Error(), "restricted") {
		t.Fatalf("body=%q error=%v", b, e)
	}
}
func TestPatchLaterHTTP403RejectedWithoutPartialResult(t *testing.T) {
	b, u, e := fetch(t, []page{{200, pageBody(admitted + "?$skiptoken=one"), nil}, {403, `{"error":{"code":"AccessDenied"}}`, nil}})
	if e == nil || b != "" || len(u) != 2 {
		t.Fatalf("%q %v %v", b, u, e)
	}
}
func TestPatchFullAdmittedContinuationPreserved(t *testing.T) {
	link := admitted + "?$skiptoken=A%2BB&$top=2"
	b, u, e := fetch(t, []page{{200, pageBody(link), nil}, {200, `{"value":[{"id":"1"}]}`, nil}})
	if e != nil || len(u) != 2 || u[1] != link || len(decode(t, b).(map[string]any)["value"].([]any)) != 2 {
		t.Fatalf("%s %v %v", b, u, e)
	}
}
func TestPatchInitialExpandQueryRetained(t *testing.T) {
	_, u, e := fetch(t, []page{{200, `{"value":[]}`, nil}})
	if e != nil || len(u) != 1 {
		t.Fatal(e, u)
	}
	parsed, e := url.Parse(u[0])
	if e != nil || parsed.Query().Get("$expand") != "children" {
		t.Fatal(u, e)
	}
}
func TestPatchUnadmittedContinuationNeverSent(t *testing.T) {
	for _, link := range []string{"http://graph.microsoft.com/beta/x", "https://untrusted.invalid/next", admitted + "/other?x=1", admitted + "#fragment", "https://user:pass@graph.microsoft.com/beta/x", "https://graph.microsoft.com:444/beta/x", "/relative/next"} {
		t.Run(link, func(t *testing.T) {
			b, u, e := fetch(t, []page{{200, pageBody(link), nil}, {200, `{"value":[]}`, nil}})
			if e == nil || b != "" || len(u) != 1 {
				t.Fatalf("%q %v %v", b, u, e)
			}
		})
	}
}
func TestPatchRepeatedContinuationRejected(t *testing.T) {
	link := admitted + "?$skiptoken=loop"
	b, u, e := fetch(t, []page{{200, pageBody(link), nil}, {200, pageBody(link), nil}, {0, "", errors.New("fixture guard")}})
	if e == nil || b != "" || len(u) != 2 {
		t.Fatalf("%q %v %v", b, u, e)
	}
}
func TestPatchMalformedPagesRejected(t *testing.T) {
	for _, body := range []string{`not-json`, `null`, `[]`, `{"error":{"code":"failure"}}`, `{"@odata.nextLink":"` + admitted + `"}`, `{"value":null}`, `{"value":{}}`, `{"value":[],"@odata.nextLink":true}`, `{"value":[],"@odata.nextLink":null}`} {
		t.Run(body, func(t *testing.T) {
			b, _, e := fetch(t, []page{{200, body, nil}})
			if e == nil || b != "" {
				t.Fatalf("%q %v", b, e)
			}
		})
	}
}
func TestPatchMalformedLaterPageRejected(t *testing.T) {
	b, u, e := fetch(t, []page{{200, pageBody(admitted + "?$skiptoken=one"), nil}, {200, `{"unknown":[]}`, nil}})
	if e == nil || b != "" || len(u) != 2 {
		t.Fatalf("%q %v %v", b, u, e)
	}
}
func TestPatchMaxPagesStopsBefore129(t *testing.T) {
	pages := []page{}
	for i := 0; i < 129; i++ {
		p, _ := json.Marshal(map[string]any{"value": []any{}, "@odata.nextLink": admitted + "?$skiptoken=" + strings.Repeat("x", i+1)})
		pages = append(pages, page{200, string(p), nil})
	}
	b, u, e := fetch(t, pages)
	if e == nil || b != "" || len(u) != 128 {
		t.Fatalf("body=%d requests=%d error=%v", len(b), len(u), e)
	}
}
func TestPatchOversizedResponseRejected(t *testing.T) {
	b, _, e := fetch(t, []page{{200, `{"value":[]}` + strings.Repeat(" ", 4*1024*1024), nil}})
	if e == nil || b != "" {
		t.Fatalf("body=%d error=%v", len(b), e)
	}
}
func TestPatchAggregateResponseBound(t *testing.T) {
	pages := []page{}
	for i := 0; i < 10; i++ {
		s := pageBody(admitted + "?$skiptoken=" + strings.Repeat("x", i+1))
		s += strings.Repeat(" ", 4*1024*1024-len(s))
		pages = append(pages, page{200, s, nil})
	}
	b, u, e := fetch(t, pages)
	if e == nil || b != "" || len(u) != 9 {
		t.Fatalf("body=%d requests=%d error=%v", len(b), len(u), e)
	}
}
func TestPatchRedirectNeverFollowed(t *testing.T) {
	old := http.DefaultTransport
	defer func() { http.DefaultTransport = old }()
	count := 0
	http.DefaultTransport = roundTrip(func(r *http.Request) (*http.Response, error) {
		count++
		return &http.Response{StatusCode: 302, Header: http.Header{"Location": []string{"https://untrusted.invalid/redir"}}, Body: io.NopCloser(strings.NewReader("")), Request: r}, nil
	})
	b, e := custom.GetRequestByResourceId(context.Background(), &fakeAdapter{}, custom.GetRequestConfig{APIVersion: custom.GraphAPIBeta, Endpoint: "/deviceManagement/configurationPolicies", ResourceID: "11111111-1111-1111-1111-111111111111", ResourceIDPattern: "('id')", EndpointSuffix: "/settings"})
	if e == nil || len(b) != 0 || count != 1 {
		t.Fatalf("body=%d requests=%d error=%v", len(b), count, e)
	}
}
func TestPatchTransportFailureRetainsUnknownOutcome(t *testing.T) {
	b, _, e := fetch(t, []page{{0, "", errors.New("response lost")}})
	if e == nil || b != "" {
		t.Fatalf("%q %v", b, e)
	}
}

func TestPatchDuplicateEnvelopeKeysRejected(t *testing.T) {
	for _, body := range []string{`{"value":{},"value":[]}`, `{"value":[],"@odata.nextLink":"https://untrusted.invalid/next","@odata.nextLink":""}`} {
		b, _, e := fetch(t, []page{{200, body, nil}})
		if e == nil || b != "" {
			t.Fatalf("duplicate envelope accepted: %q %v", b, e)
		}
	}
}
