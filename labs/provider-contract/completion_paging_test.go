package contract

import (
	"context"
	"errors"
	custom "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/custom_requests"
	auth "github.com/microsoft/kiota-abstractions-go/authentication"
	httpadapter "github.com/microsoft/kiota-http-go"
	"io"
	"net/http"
	"strings"
	"testing"
)

func configuredFetch(t *testing.T, suffix string, pages []page) (string, []string, error) {
	t.Helper()
	urls := []string{}
	old := http.DefaultTransport
	http.DefaultTransport = roundTrip(func(*http.Request) (*http.Response, error) { return nil, errors.New("default transport forbidden") })
	t.Cleanup(func() { http.DefaultTransport = old })
	client := &http.Client{Transport: roundTrip(func(req *http.Request) (*http.Response, error) {
		urls = append(urls, req.URL.String())
		if len(urls) > len(pages) {
			return nil, errors.New("unexpected request")
		}
		p := pages[len(urls)-1]
		if p.err != nil {
			return nil, p.err
		}
		return &http.Response{StatusCode: p.status, Body: io.NopCloser(strings.NewReader(p.body)), Header: http.Header{"Content-Type": []string{"application/json"}}, Request: req}, nil
	})}
	adapter, e := httpadapter.NewNetHttpRequestAdapterWithParseNodeFactoryAndSerializationWriterFactoryAndHttpClient(&auth.AnonymousAuthenticationProvider{}, nil, nil, client)
	if e != nil {
		t.Fatal(e)
	}
	b, e := completionFetch(context.Background(), adapter, custom.GetRequestConfig{APIVersion: custom.GraphAPIBeta, Endpoint: "/deviceManagement/configurationPolicies", ResourceID: "fixture", ResourceIDPattern: "('id')", EndpointSuffix: suffix, QueryParameters: map[string]string{"$expand": "children"}})
	return string(b), urls, e
}
func TestCompletionConfiguredAdapterAndAssignmentPaging(t *testing.T) {
	link := "https://graph.microsoft.com/beta/deviceManagement/configurationPolicies('fixture')/assignments?$skiptoken=opaque%2Bvalue"
	body := `{"value":[{"id":"a"}],"@odata.nextLink":"` + link + `"}`
	got, urls, e := configuredFetch(t, "/assignments", []page{{200, body, nil}, {200, `{"value":[{"id":"b"}]}`, nil}})
	if e != nil || len(urls) != 2 {
		t.Fatalf("configured adapter not used for complete paging: %v %v", urls, e)
	}
	if urls[1] != link || !strings.Contains(urls[0], "%24expand=children") {
		t.Fatalf("queries changed: %v", urls)
	}
	if len(decode(t, got).(map[string]any)["value"].([]any)) != 2 {
		t.Fatal(got)
	}
}
func TestCompletionAssignmentFailuresNeverReturnPartial(t *testing.T) {
	for _, fixture := range []struct {
		name, body string
		status     int
	}{
		{"denied", `{"error":{"code":"AccessDenied"}}`, 403}, {"duplicate", `{"value":[{"id":"a"}]}`, 200}, {"null", `{"value":null}`, 200}, {"bad_status", `{"value":[]}`, 202}, {"missing_id", `{"value":[{}]}`, 200},
	} {
		t.Run(fixture.name, func(t *testing.T) {
			first := `{"value":[{"id":"a"}],"@odata.nextLink":"https://graph.microsoft.com/beta/deviceManagement/configurationPolicies('fixture')/assignments?$skiptoken=2"}`
			got, urls, e := configuredFetch(t, "/assignments", []page{{200, first, nil}, {fixture.status, fixture.body, nil}})
			if e == nil || got != "" || len(urls) != 2 {
				t.Fatalf("incomplete assignment chain accepted: %v %s", e, got)
			}
		})
	}
}

func TestCompletionContinuationAndCountRejection(t *testing.T) {
	root := "https://graph.microsoft.com/beta/deviceManagement/configurationPolicies('fixture')/assignments"
	cases := []struct{ name, body string }{
		{"foreign", `{"value":[],"@odata.nextLink":"https://foreign.invalid/steal"}`},
		{"wrong_path", `{"value":[],"@odata.nextLink":"https://graph.microsoft.com/beta/users"}`},
		{"relative", `{"value":[],"@odata.nextLink":"?skip=2"}`},
		{"null_link", `{"value":[],"@odata.nextLink":null}`},
		{"duplicate_envelope", `{"value":[],"value":[]}`},
		{"duplicate_item_key", `{"value":[{"id":"a","id":"b"}]}`},
		{"count_short", `{"value":[],"@odata.count":1}`},
		{"loop", `{"value":[],"@odata.nextLink":"` + root + `?%24expand=children"}`},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			b, urls, e := configuredFetch(t, "/assignments", []page{{200, c.body, nil}})
			if e == nil || b != "" || len(urls) != 1 {
				t.Fatalf("invalid chain accepted or unsafe follow attempted: %v %v", urls, e)
			}
		})
	}
}
