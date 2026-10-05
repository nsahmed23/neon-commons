package contract

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"reflect"
	"strings"
	"testing"

	custom "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/custom_requests"
	"github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/normalize"
	modifier "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/plan_modifiers"
	model "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/shared_models/graph_beta/device_management"
	state "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/state/graph_beta/device_management"
	validate "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/validate/graph_beta/device_management"
	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/schema/validator"
	"github.com/hashicorp/terraform-plugin-framework/types"
	abstractions "github.com/microsoft/kiota-abstractions-go"
	serialization "github.com/microsoft/kiota-abstractions-go/serialization"
	writer "github.com/microsoft/kiota-serialization-json-go"
)

const config = `{"settings":[{"id":"0","settingInstance":{"@odata.type":"#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance","settingDefinitionId":"device_vendor_msft_policy_config_privacy_letappsaccesslocation","settingInstanceTemplateReference":null,"choiceSettingValue":{"@odata.type":"#microsoft.graph.deviceManagementConfigurationChoiceSettingValue","settingValueTemplateReference":null,"value":"device_vendor_msft_policy_config_privacy_letappsaccesslocation_2","children":[]}}}]}`

func valid(s string) bool {
	r := validator.StringResponse{}
	validate.SettingsCatalogJSONValidator().ValidateString(context.Background(), validator.StringRequest{Path: path.Root("settings"), ConfigValue: types.StringValue(s)}, &r)
	return !r.Diagnostics.HasError()
}
func mapped(s string) string {
	m := model.SettingsCatalogJsonResourceModel{Settings: types.StringValue(config)}
	state.StateConfigurationPolicySettings(context.Background(), &m, []byte(s))
	return m.Settings.ValueString()
}
func decode(t *testing.T, s string) any {
	t.Helper()
	var v any
	if e := json.Unmarshal([]byte(s), &v); e != nil {
		t.Fatal(e)
	}
	return v
}
func norm(t *testing.T, s string) string {
	t.Helper()
	v, e := normalize.JSONAlphabetically(s)
	if e != nil {
		t.Fatal(e)
	}
	return v
}

func TestValidatorAcceptsCorrectedConfiguration(t *testing.T) {
	if !valid(config) {
		t.Fatal("corrected config rejected")
	}
}
func TestValidatorRejectsResponseWrapper(t *testing.T) {
	v := strings.Replace(config, `"id":"0"`, `"@odata.type":"#microsoft.graph.deviceManagementConfigurationSetting","id":"0"`, 1)
	if valid(v) {
		t.Fatal("wrapper unexpectedly accepted")
	}
}
func TestKnownHazardValidatorAcceptsNonzeroFirstID(t *testing.T) {
	if !valid(strings.Replace(config, `"id":"0"`, `"id":"9"`, 1)) {
		t.Fatal("pinned nonzero behavior changed")
	}
}
func TestValidatorRejectsMissingID(t *testing.T) {
	if valid(strings.Replace(config, `"id":"0",`, "", 1)) {
		t.Fatal("missing ID accepted")
	}
}
func TestValidatorRejectsNonSequentialIDs(t *testing.T) {
	v := decode(t, config).(map[string]any)
	first := v["settings"].([]any)[0]
	second := decode(t, config).(map[string]any)["settings"].([]any)[0].(map[string]any)
	second["id"] = "2"
	v["settings"] = []any{first, second}
	b, _ := json.Marshal(v)
	if valid(string(b)) {
		t.Fatal("nonsequential IDs accepted")
	}
}
func TestKnownHazardValidatorAcceptsNullInstance(t *testing.T) {
	if !valid(`{"settings":[{"id":"0","settingInstance":null}]}`) {
		t.Fatal("pinned shape gap changed")
	}
}
func TestStateRetainsResponseWrapper(t *testing.T) {
	response := `{"value":[{"id":"0","@odata.type":"#microsoft.graph.deviceManagementConfigurationSetting","settingInstance":{}}]}`
	m := decode(t, mapped(response)).(map[string]any)
	s := m["settings"].([]any)[0].(map[string]any)
	if s["@odata.type"] == nil || s["id"] != "0" {
		t.Fatal(s)
	}
}
func TestKnownHazardMalformedResponseRetainsOldState(t *testing.T) {
	if mapped(`not-json`) != config {
		t.Fatal("pinned fallback changed")
	}
}
func TestKnownHazardErrorBodyMappedAsSettings(t *testing.T) {
	m := decode(t, mapped(`{"error":{"code":"AccessDenied"}}`)).(map[string]any)
	if m["settings"].(map[string]any)["error"] == nil {
		t.Fatal(m)
	}
}
func TestNormalizerPreservesOrder(t *testing.T) {
	a := norm(t, `{"settings":[{"id":"0"},{"id":"1"}]}`)
	b := norm(t, `{"settings":[{"id":"1"},{"id":"0"}]}`)
	if a == b {
		t.Fatal("array order collapsed")
	}
}
func TestNormalizerDistinguishesNullOmittedEmpty(t *testing.T) {
	seen := map[string]bool{}
	for _, s := range []string{`{}`, `{"children":null}`, `{"children":[]}`} {
		seen[norm(t, s)] = true
	}
	if len(seen) != 3 {
		t.Fatal(seen)
	}
}
func TestPlanModifierDoesNotReconcileResponseShape(t *testing.T) {
	r := planmodifier.StringResponse{}
	modifier.NormalizeJSONPlanModifier{}.PlanModifyString(context.Background(), planmodifier.StringRequest{ConfigValue: types.StringValue(config)}, &r)
	response := strings.Replace(config, `"id":"0"`, `"@odata.type":"#microsoft.graph.deviceManagementConfigurationSetting","id":"0"`, 1)
	if r.PlanValue.ValueString() == norm(t, response) {
		t.Fatal("response shape reconciled unexpectedly")
	}
}

type fakeAdapter struct{ abstractions.RequestAdapter }

func (a *fakeAdapter) ConvertToNativeRequest(ctx context.Context, r *abstractions.RequestInformation) (any, error) {
	u, e := r.GetUri()
	if e != nil {
		return nil, e
	}
	return http.NewRequestWithContext(ctx, "GET", u.String(), nil)
}

type roundTrip func(*http.Request) (*http.Response, error)

func (f roundTrip) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

type page struct {
	status int
	body   string
	err    error
}

func fetch(t *testing.T, pages []page) (string, []string, error) {
	t.Helper()
	original := http.DefaultTransport
	defer func() { http.DefaultTransport = original }()
	urls := []string{}
	http.DefaultTransport = roundTrip(func(r *http.Request) (*http.Response, error) {
		urls = append(urls, r.URL.String())
		i := len(urls) - 1
		if i >= len(pages) {
			return nil, errors.New("fixture exhausted; no network transport exists")
		}
		p := pages[i]
		if p.err != nil {
			return nil, p.err
		}
		return &http.Response{StatusCode: p.status, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(p.body)), Request: r}, nil
	})
	b, e := custom.GetRequestByResourceId(context.Background(), &fakeAdapter{}, custom.GetRequestConfig{APIVersion: custom.GraphAPIBeta, Endpoint: "/deviceManagement/configurationPolicies", ResourceID: "11111111-1111-1111-1111-111111111111", ResourceIDPattern: "('id')", EndpointSuffix: "/settings", QueryParameters: map[string]string{"$expand": "children"}})
	return string(b), urls, e
}

const next = "https://graph.microsoft.com/beta/deviceManagement/configurationPolicies/p/settings?$skiptoken=A%2BB&$top=2"

func TestSettingsPaginationUsesFullNextLink(t *testing.T) {
	first, _ := json.Marshal(map[string]any{"value": []any{map[string]any{"id": "0"}}, "@odata.nextLink": next})
	b, u, e := fetch(t, []page{{200, string(first), nil}, {200, `{"value":[{"id":"1"}]}`, nil}})
	if e != nil || len(u) != 2 || u[1] != next {
		t.Fatalf("%v %v", u, e)
	}
	v := decode(t, b).(map[string]any)["value"].([]any)
	if len(v) != 2 {
		t.Fatal(v)
	}
}
func TestKnownHazardFirstHTTP403ReturnsNoError(t *testing.T) {
	b, u, e := fetch(t, []page{{403, `{"error":{"code":"AccessDenied"}}`, nil}})
	if e != nil || len(u) != 1 || !strings.Contains(b, "AccessDenied") {
		t.Fatalf("%v %v %s", u, e, b)
	}
}
func TestKnownHazardLaterHTTP403SilentlyTruncates(t *testing.T) {
	first, _ := json.Marshal(map[string]any{"value": []any{map[string]any{"id": "0"}}, "@odata.nextLink": next})
	b, u, e := fetch(t, []page{{200, string(first), nil}, {403, `{"error":{"code":"AccessDenied"}}`, nil}})
	if e != nil || len(u) != 2 {
		t.Fatalf("%v %v", u, e)
	}
	if !reflect.DeepEqual(decode(t, b), decode(t, `{"value":[{"id":"0"}]}`)) {
		t.Fatal(b)
	}
}
func TestPaginationTransportFailurePropagates(t *testing.T) {
	first, _ := json.Marshal(map[string]any{"value": []any{}, "@odata.nextLink": next})
	b, _, e := fetch(t, []page{{200, string(first), nil}, {0, "", errors.New("lost response")}})
	if e == nil || b != "" {
		t.Fatalf("%v %s", e, b)
	}
}
func TestKnownHazardForeignNextLinkIsRequested(t *testing.T) {
	foreign := "https://untrusted.invalid/next?x=1"
	first, _ := json.Marshal(map[string]any{"value": []any{}, "@odata.nextLink": foreign})
	_, u, e := fetch(t, []page{{200, string(first), nil}, {200, `{"value":[]}`, nil}})
	if e != nil || len(u) != 2 || u[1] != foreign {
		t.Fatalf("%v %v", u, e)
	}
}
func TestKnownHazardRepeatedNextLinkIsRetried(t *testing.T) {
	first, _ := json.Marshal(map[string]any{"value": []any{}, "@odata.nextLink": next})
	_, u, e := fetch(t, []page{{200, string(first), nil}, {200, string(first), nil}, {0, "", errors.New("fixture stops loop")}})
	if e == nil || len(u) != 3 || u[1] != u[2] {
		t.Fatalf("%v %v", u, e)
	}
}
func TestKnownHazardMissingValueIgnoresContinuation(t *testing.T) {
	first, _ := json.Marshal(map[string]any{"@odata.nextLink": next})
	_, u, e := fetch(t, []page{{200, string(first), nil}})
	if e != nil || len(u) != 1 {
		t.Fatalf("%v %v", u, e)
	}
}

func TestJSONWriterNilStringOmitted(t *testing.T) {
	w := writer.NewJsonSerializationWriter()
	if e := w.WriteStringValue("id", nil); e != nil {
		t.Fatal(e)
	}
	b, e := w.GetSerializedContent()
	if e != nil || len(b) != 0 {
		t.Fatalf("%s %v", b, e)
	}
}
func TestJSONWriterEmptyCollectionPreserved(t *testing.T) {
	w := writer.NewJsonSerializationWriter()
	if e := w.WriteCollectionOfObjectValues("", []serialization.Parsable{}); e != nil {
		t.Fatal(e)
	}
	b, e := w.GetSerializedContent()
	if e != nil || string(b) != "[]" {
		t.Fatalf("%s %v", b, e)
	}
}

func TestKnownHazardInitialExpandQueryIsLost(t *testing.T) {
	_, urls, err := fetch(t, []page{{200, `{"value":[]}`, nil}})
	if err != nil || len(urls) != 1 {
		t.Fatalf("%v %v", urls, err)
	}
	if strings.Contains(urls[0], "expand") {
		t.Fatal("initial query omission changed", urls)
	}
}
