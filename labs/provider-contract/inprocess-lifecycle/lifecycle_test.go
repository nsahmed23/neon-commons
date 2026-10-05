// In-process qualification of the real patched resource through an injected
// Kiota HTTP transport. No socket, credential, service, or RPC qualification.
package epochlifecycle

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"reflect"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/deploymenttheory/terraform-provider-microsoft365/internal/client"
	selected "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/resources/device_management/graph_beta/settings_catalog_configuration_policy_json"
	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/tfsdk"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/hashicorp/terraform-plugin-go/tftypes"
	auth "github.com/microsoft/kiota-abstractions-go/authentication"
	httpadapter "github.com/microsoft/kiota-http-go"
	graph "github.com/microsoftgraph/msgraph-beta-sdk-go"
)

type fixture struct {
	ID                        string         `json:"id"`
	Policy                    map[string]any `json:"policy"`
	Settings                  map[string]any `json:"settings"`
	Assignments               []any          `json:"assignments"`
	UnmanagedEmptyAssignments bool           `json:"-"` // Independent expected null-config semantics, never a service field.
}
type requestRecord struct {
	Method string
	URL    string
	Body   any
}
type service struct {
	data    fixture
	truth   fixture // Immutable fixture loaded separately, never updated by transport.
	rows    []requestRecord
	fault   string
	writes  int
	deleted bool
}

const createdID = "55555555-5555-4555-8555-555555555555"

func cloneFixture(value fixture) fixture {
	raw, _ := json.Marshal(value)
	var result fixture
	if err := json.Unmarshal(raw, &result); err != nil {
		panic(err)
	}
	return result
}

func (s *service) RoundTrip(req *http.Request) (*http.Response, error) {
	if req.URL.Scheme != "https" || req.URL.Host != "graph.microsoft.com" {
		return nil, fmt.Errorf("foreign request denied")
	}
	var body map[string]any
	if req.Body != nil {
		raw, err := io.ReadAll(io.LimitReader(req.Body, 1<<20))
		if err != nil {
			return nil, err
		}
		if len(raw) > 0 {
			if err = json.Unmarshal(raw, &body); err != nil {
				return nil, err
			}
		}
	}
	s.rows = append(s.rows, requestRecord{req.Method, req.URL.String(), body})
	root := "/beta/deviceManagement/configurationPolicies"
	id := s.data.ID
	status := 200
	var response any
	switch {
	case req.Method == "POST" && req.URL.Path == root:
		s.writes++
		s.data.ID = createdID
		// A new object cannot inherit any client-controlled fields or settings
		// from the previously imported fixture. Server metadata is explicit.
		s.data.Policy = map[string]any{"id": createdID, "settingCount": 0,
			"createdDateTime": "2026-09-30T12:00:00Z", "lastModifiedDateTime": "2026-09-30T12:00:00Z"}
		s.data.Settings = map[string]any{"value": []any{}}
		// A newly created policy has no assignments until a separate assign succeeds.
		s.data.Assignments = []any{}
		s.data.Policy["isAssigned"] = false
		s.deleted = false
		for _, k := range []string{"name", "description", "platforms", "technologies", "roleScopeTagIds"} {
			if v, ok := body[k]; ok {
				s.data.Policy[k] = v
			}
		}
		if v, ok := body["settings"]; ok {
			s.data.Settings["value"] = v
			if rows, valid := v.([]any); valid {
				s.data.Policy["settingCount"] = len(rows)
			}
		}
		if s.fault == "lost-create-response" {
			return nil, fmt.Errorf("synthetic response lost after committed create")
		}
		switch s.fault {
		case "missing-created-id":
			response = map[string]any{"name": "created without id"}
		case "null-created-id":
			response = map[string]any{"id": nil}
		case "empty-created-id":
			response = map[string]any{"id": ""}
		case "whitespace-created-id":
			response = map[string]any{"id": " "}
		case "nil-created-policy":
			response = nil
		default:
			response = s.data.Policy
		}
	case req.Method == "PUT" && req.URL.Path == root+"('"+id+"')":
		s.writes++
		for _, k := range []string{"name", "description", "platforms", "technologies", "roleScopeTagIds"} {
			if v, ok := body[k]; ok {
				s.data.Policy[k] = v
			}
		}
		if v, ok := body["settings"]; ok {
			s.data.Settings["value"] = v
		}
		status = 204
	case req.Method == "POST" && req.URL.Path == root+"/"+id+"/assign":
		if s.fault == "assignment-denied" {
			status = 403
			response = map[string]any{"error": map[string]any{"code": "Authorization_RequestDenied", "message": "synthetic denied assignment"}}
		} else {
			s.writes++
			// Assignment IDs are service-owned readback fields. Keep request
			// targets exactly as received; only supply the absent server IDs.
			rawAssignments, ok := body["assignments"].([]any)
			if !ok {
				return nil, fmt.Errorf("invalid modeled assignment request")
			}
			s.data.Assignments = make([]any, len(rawAssignments))
			for index, raw := range rawAssignments {
				row, ok := raw.(map[string]any)
				if !ok {
					return nil, fmt.Errorf("invalid assignment row")
				}
				copyRow := make(map[string]any, len(row)+1)
				for key, value := range row {
					copyRow[key] = value
				}
				copyRow["id"] = fmt.Sprintf("modeled-assignment-%d", index)
				s.data.Assignments[index] = copyRow
			}
			s.data.Policy["isAssigned"] = len(s.data.Assignments) > 0
			if s.fault == "lost-assignment-response" {
				return nil, fmt.Errorf("synthetic response lost after committed assignment")
			}
			response = map[string]any{"value": s.data.Assignments}
		}
	case req.Method == "GET" && req.URL.Path == root+"/"+id:
		if s.fault == "base-get-400" {
			status = 400
			response = graphError("BadRequest", "synthetic base query rejected")
		} else if s.deleted {
			status = 404
			response = map[string]any{"error": map[string]any{"code": "ResourceNotFound", "message": "modeled deleted policy"}}
		} else if s.fault == "wrong-read-id" {
			response = map[string]any{"id": "different-policy"}
		} else if s.fault == "missing-name" || s.fault == "missing-platforms" || s.fault == "missing-technologies" || s.fault == "missing-isAssigned" || s.fault == "missing-settingCount" {
			policy := cloneFixture(s.data).Policy
			delete(policy, strings.TrimPrefix(s.fault, "missing-"))
			response = policy
		} else if s.fault == "wrong-isAssigned" || s.fault == "wrong-settingCount" {
			policy := cloneFixture(s.data).Policy
			if s.fault == "wrong-isAssigned" {
				policy["isAssigned"] = false
			} else {
				policy["settingCount"] = 99
			}
			response = policy
		} else {
			response = s.data.Policy
		}
	case req.Method == "GET" && req.URL.Path == root+"('"+id+"')/settings":
		switch s.fault {
		case "settings-get-400":
			status = 400
			response = graphError("BadRequest", "synthetic settings query rejected")
		case "settings-get-404":
			status = 404
			response = graphError("ResourceNotFound", "synthetic settings collection unavailable; policy exists")
		case "missing-settings-page":
			response = map[string]any{}
		default:
			response = s.data.Settings
		}
	case req.Method == "GET" && req.URL.Path == root+"('"+id+"')/assignments":
		if s.fault == "missing-assignment-page" {
			response = map[string]any{}
		} else if len(s.data.Assignments) <= 1 {
			response = map[string]any{"value": s.data.Assignments}
		} else if req.URL.Query().Get("$skiptoken") == "2" {
			response = map[string]any{"value": s.data.Assignments[1:]}
		} else {
			response = map[string]any{"value": s.data.Assignments[:1], "@odata.nextLink": "https://graph.microsoft.com" + req.URL.Path + "?$skiptoken=2"}
		}
	case req.Method == "DELETE" && req.URL.Path == root+"/"+id:
		s.writes++
		s.deleted = true
		status = 204
	default:
		return nil, fmt.Errorf("unmodeled request denied: %s %s", req.Method, req.URL.String())
	}
	raw := []byte{}
	if response != nil {
		raw, _ = json.Marshal(response)
	}
	return &http.Response{StatusCode: status, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(string(raw))), ContentLength: int64(len(raw)), Request: req}, nil
}

func graphError(code, message string) map[string]any {
	return map[string]any{"error": map[string]any{"code": code, "message": message}}
}

func (s *service) countRequests(method, suffix string) int {
	count := 0
	for _, row := range s.rows {
		parsed, err := url.Parse(row.URL)
		if err == nil && row.Method == method && strings.HasSuffix(parsed.Path, suffix) {
			count++
		}
	}
	return count
}

func setup(t *testing.T) (context.Context, *selected.SettingsCatalogJsonResource, *service, tfsdk.State) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
	t.Cleanup(cancel)
	raw, err := os.ReadFile("fixture.json")
	if err != nil {
		t.Fatal(err)
	}
	s := &service{}
	if err = json.Unmarshal(raw, &s.data); err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(raw, &s.truth); err != nil {
		t.Fatal(err)
	}
	hc := &http.Client{Transport: s, CheckRedirect: func(*http.Request, []*http.Request) error { return fmt.Errorf("redirect denied") }}
	adapter, err := httpadapter.NewNetHttpRequestAdapterWithParseNodeFactoryAndSerializationWriterFactoryAndHttpClient(&auth.AnonymousAuthenticationProvider{}, nil, nil, hc)
	if err != nil {
		t.Fatal(err)
	}
	r := selected.NewSettingsCatalogJsonResource().(*selected.SettingsCatalogJsonResource)
	conf := resource.ConfigureResponse{}
	r.Configure(ctx, resource.ConfigureRequest{ProviderData: &client.GraphClients{KiotaGraphBetaClient: graph.NewGraphServiceClient(adapter)}}, &conf)
	if conf.Diagnostics.HasError() {
		t.Fatal(conf.Diagnostics)
	}
	sr := resource.SchemaResponse{}
	r.Schema(ctx, resource.SchemaRequest{}, &sr)
	if sr.Diagnostics.HasError() {
		t.Fatal(sr.Diagnostics)
	}
	st := tfsdk.State{Schema: sr.Schema, Raw: tftypes.NewValue(sr.Schema.Type().TerraformType(ctx), nil)}
	ir := resource.ImportStateResponse{State: st}
	r.ImportState(ctx, resource.ImportStateRequest{ID: s.data.ID}, &ir)
	if ir.Diagnostics.HasError() {
		t.Fatal(ir.Diagnostics)
	}
	rr := resource.ReadResponse{State: ir.State}
	r.Read(ctx, resource.ReadRequest{State: ir.State}, &rr)
	if rr.Diagnostics.HasError() {
		t.Fatal(rr.Diagnostics)
	}
	t.Cleanup(func() {
		row, _ := json.Marshal(map[string]any{"test": t.Name(), "requests": s.rows, "writes": s.writes})
		t.Log(string(row))
	})
	return ctx, r, s, rr.State
}

// expected is independently frozen before the first mutation. Never derive it
// from the mutable transport: a dropped request field must not become truth.
func assertObserved(t *testing.T, ctx context.Context, st tfsdk.State, expected fixture) {
	t.Helper()
	var id, name, settings types.String
	var assignments types.Set
	if d := st.GetAttribute(ctx, path.Root("id"), &id); d.HasError() {
		t.Fatal(d)
	}
	if id.IsUnknown() || id.IsNull() || id.ValueString() != expected.ID {
		t.Fatalf("immutable ID lost: %q", id.ValueString())
	}
	if d := st.GetAttribute(ctx, path.Root("name"), &name); d.HasError() {
		t.Fatal(d)
	}
	if name.ValueString() != expected.Policy["name"] {
		t.Fatal("name/readback mismatch")
	}
	if d := st.GetAttribute(ctx, path.Root("settings"), &settings); d.HasError() {
		t.Fatal(d)
	}
	var envelope map[string]any
	if err := json.Unmarshal([]byte(settings.ValueString()), &envelope); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(envelope["settings"], expected.Settings["value"]) {
		t.Fatalf("settings differ from independently authored service observation")
	}
	if d := st.GetAttribute(ctx, path.Root("assignments"), &assignments); d.HasError() {
		t.Fatal(d)
	}
	if expected.UnmanagedEmptyAssignments {
		if len(expected.Assignments) != 0 || !assignments.IsNull() {
			t.Fatal("omitted assignment intent was not preserved after confirmed empty observation")
		}
	} else if assignments.IsNull() || assignments.IsUnknown() || len(assignments.Elements()) != len(expected.Assignments) {
		t.Fatal("paginated assignment count changed")
	}
	actualTuples := make([]string, 0, len(assignments.Elements()))
	for _, element := range assignments.Elements() {
		object, ok := element.(types.Object)
		if !ok || object.IsUnknown() || object.IsNull() {
			t.Fatal("invalid assignment state object")
		}
		fields := object.Attributes()
		tuple := make([]any, 0, 4)
		for _, key := range []string{"type", "group_id", "filter_type", "filter_id"} {
			value, ok := fields[key].(types.String)
			if !ok || value.IsUnknown() {
				t.Fatalf("invalid typed assignment field %s", key)
			}
			if value.IsNull() {
				tuple = append(tuple, nil)
			} else {
				tuple = append(tuple, value.ValueString())
			}
		}
		if len(fields) != 4 {
			t.Fatal("unexpected assignment state field")
		}
		raw, _ := json.Marshal(tuple)
		actualTuples = append(actualTuples, string(raw))
	}
	expectedTuples := assignmentTuples(t, expected.Assignments)
	sort.Strings(actualTuples)
	if !reflect.DeepEqual(actualTuples, expectedTuples) {
		t.Fatalf("targeting tuple mismatch: got %v expected %v", actualTuples, expectedTuples)
	}
	for field, remote := range map[string]string{"description": "description", "platforms": "platforms"} {
		var value types.String
		if d := st.GetAttribute(ctx, path.Root(field), &value); d.HasError() {
			t.Fatal(d)
		}
		if value.IsUnknown() || value.IsNull() || value.ValueString() != expected.Policy[remote] {
			t.Fatalf("%s changed", field)
		}
	}
	var isAssigned types.Bool
	var settingCount types.Int32
	if d := st.GetAttribute(ctx, path.Root("is_assigned"), &isAssigned); d.HasError() {
		t.Fatal(d)
	}
	if d := st.GetAttribute(ctx, path.Root("settings_count"), &settingCount); d.HasError() {
		t.Fatal(d)
	}
	if isAssigned.IsNull() || isAssigned.IsUnknown() || isAssigned.ValueBool() != (len(expected.Assignments) > 0) {
		t.Fatal("isAssigned disagrees with independently observed targeting")
	}
	if settingCount.IsNull() || settingCount.IsUnknown() || int(settingCount.ValueInt32()) != len(expected.Settings["value"].([]any)) {
		t.Fatal("settingCount disagrees with independently observed settings")
	}
	var tags types.Set
	var technologies types.List
	if d := st.GetAttribute(ctx, path.Root("role_scope_tag_ids"), &tags); d.HasError() {
		t.Fatal(d)
	}
	if d := st.GetAttribute(ctx, path.Root("technologies"), &technologies); d.HasError() {
		t.Fatal(d)
	}
	var actualTags, actualTechnologies []string
	if d := tags.ElementsAs(ctx, &actualTags, false); d.HasError() {
		t.Fatal(d)
	}
	if d := technologies.ElementsAs(ctx, &actualTechnologies, false); d.HasError() {
		t.Fatal(d)
	}
	expectedTags := []string{}
	for _, tag := range expected.Policy["roleScopeTagIds"].([]any) {
		expectedTags = append(expectedTags, tag.(string))
	}
	expectedTechnologies := strings.Split(expected.Policy["technologies"].(string), ",")
	sort.Strings(actualTags)
	sort.Strings(expectedTags)
	sort.Strings(actualTechnologies)
	sort.Strings(expectedTechnologies)
	if !reflect.DeepEqual(actualTags, expectedTags) || !reflect.DeepEqual(actualTechnologies, expectedTechnologies) {
		t.Fatal("scope tags or technologies changed")
	}
}

func assignmentTuples(t *testing.T, rows []any) []string {
	t.Helper()
	result := make([]string, 0, len(rows))
	for _, row := range rows {
		target := row.(map[string]any)["target"].(map[string]any)
		tuple := []any{strings.TrimPrefix(target["@odata.type"].(string), "#microsoft.graph."), target["groupId"], target["deviceAndAppManagementAssignmentFilterType"], target["deviceAndAppManagementAssignmentFilterId"]}
		raw, _ := json.Marshal(tuple)
		result = append(result, string(raw))
	}
	sort.Strings(result)
	return result
}

func createPlan(t *testing.T, ctx context.Context, st tfsdk.State) tfsdk.Plan {
	t.Helper()
	plan := tfsdk.Plan{Schema: st.Schema, Raw: st.Raw}
	if d := plan.SetAttribute(ctx, path.Root("id"), types.StringUnknown()); d.HasError() {
		t.Fatal(d)
	}
	return plan
}

func TestEpochImportReadUpdateRefreshDelete(t *testing.T) {
	ctx, r, s, st := setup(t)
	expected := cloneFixture(s.truth)
	assertObserved(t, ctx, st, expected)
	plan := tfsdk.Plan{Schema: st.Schema, Raw: st.Raw}
	if d := plan.SetAttribute(ctx, path.Root("name"), types.StringValue("Changed through real resource Update")); d.HasError() {
		t.Fatal(d)
	}
	ur := resource.UpdateResponse{State: st}
	r.Update(ctx, resource.UpdateRequest{State: st, Plan: plan}, &ur)
	if ur.Diagnostics.HasError() {
		t.Fatal(ur.Diagnostics)
	}
	expected.Policy["name"] = "Changed through real resource Update"
	assertObserved(t, ctx, ur.State, expected)
	if !reflect.DeepEqual(s.data.Settings, expected.Settings) || !reflect.DeepEqual(assignmentTuples(t, s.data.Assignments), assignmentTuples(t, expected.Assignments)) {
		t.Fatal("outgoing mutation did not preserve independently frozen settings/targets")
	}
	rr := resource.ReadResponse{State: ur.State}
	r.Read(ctx, resource.ReadRequest{State: ur.State}, &rr)
	if rr.Diagnostics.HasError() {
		t.Fatal(rr.Diagnostics)
	}
	if !rr.State.Raw.Equal(ur.State.Raw) {
		t.Fatal("second refresh changed state")
	}
	if s.writes != 2 {
		t.Fatalf("expected one PUT + one assignment POST, got %d", s.writes)
	}
	dr := resource.DeleteResponse{State: rr.State}
	r.Delete(ctx, resource.DeleteRequest{State: rr.State}, &dr)
	if dr.Diagnostics.HasError() {
		t.Fatal(dr.Diagnostics)
	}
	if !dr.State.Raw.IsNull() {
		t.Fatal("delete did not remove state")
	}
	if !s.deleted || s.writes != 3 {
		t.Fatal("delete did not reach modeled service exactly once")
	}
	read := resource.ReadResponse{State: rr.State}
	r.Read(ctx, resource.ReadRequest{State: rr.State}, &read)
	if read.Diagnostics.HasError() || !read.State.Raw.IsNull() {
		t.Fatal("readback did not confirm remote absence after delete")
	}
}

func TestEpochCreateReadback(t *testing.T) {
	ctx, r, s, st := setup(t)
	plan := createPlan(t, ctx, st)
	out := resource.CreateResponse{State: tfsdk.State{Schema: st.Schema, Raw: tftypes.NewValue(st.Raw.Type(), nil)}}
	r.Create(ctx, resource.CreateRequest{Plan: plan}, &out)
	if out.Diagnostics.HasError() {
		t.Fatal(out.Diagnostics)
	}
	expected := cloneFixture(s.truth)
	expected.ID = createdID
	expected.Policy["id"] = createdID
	assertObserved(t, ctx, out.State, expected)
	if s.writes != 2 {
		t.Fatal("unexpected create dispatch count")
	}
}

func TestEpochCreateMissingIdentityIsErrorNotPanic(t *testing.T) {
	for _, fault := range []string{"missing-created-id", "null-created-id", "empty-created-id", "whitespace-created-id", "nil-created-policy"} {
		t.Run(fault, func(t *testing.T) {
			ctx, r, s, st := setup(t)
			s.fault = fault
			defer func() {
				if e := recover(); e != nil {
					t.Errorf("provider panicked on incomplete create response: %v", e)
				}
			}()
			out := resource.CreateResponse{State: tfsdk.State{Schema: st.Schema, Raw: tftypes.NewValue(st.Raw.Type(), nil)}}
			r.Create(ctx, resource.CreateRequest{Plan: createPlan(t, ctx, st)}, &out)
			if !out.Diagnostics.HasError() {
				t.Error("missing immutable identity accepted")
			}
			if s.writes != 1 || s.countRequests("POST", "/assign") != 0 {
				t.Error("assignment dispatched with unverified created identity")
			}
			if !out.State.Raw.IsNull() {
				t.Error("unverified create identity was projected into state")
			}
		})
	}
}

func TestEpochPartialCreateRetainsKnownRemoteIdentity(t *testing.T) {
	ctx, r, s, st := setup(t)
	s.fault = "assignment-denied"
	out := resource.CreateResponse{State: tfsdk.State{Schema: st.Schema, Raw: tftypes.NewValue(st.Raw.Type(), nil)}}
	r.Create(ctx, resource.CreateRequest{Plan: createPlan(t, ctx, st)}, &out)
	if !out.Diagnostics.HasError() {
		t.Fatal("partial create reported success")
	}
	var id types.String
	if d := out.State.GetAttribute(ctx, path.Root("id"), &id); d.HasError() {
		t.Fatal(d)
	}
	if id.IsUnknown() || id.IsNull() || id.ValueString() != createdID {
		t.Fatalf("created remote object orphaned from state: known id %s, state id %q", createdID, id.ValueString())
	}
	if s.writes != 1 || s.countRequests("POST", "/assign") != 1 {
		t.Fatal("duplicate or unexpected mutation")
	}
	if len(s.data.Assignments) != 0 {
		t.Fatal("test model falsely gave a new policy inherited assignments")
	}
	assertFailedCreateState(t, ctx, out.State, s, false)
}

// Error state may retain an ID-only anchor, or a complete independent observed
// state. It may never substitute planned attributes for an incomplete read.
func assertFailedCreateState(t *testing.T, ctx context.Context, st tfsdk.State, s *service, assignmentCommitted bool) {
	t.Helper()
	var id types.String
	if d := st.GetAttribute(ctx, path.Root("id"), &id); d.HasError() {
		t.Fatal(d)
	}
	if id.IsNull() || id.IsUnknown() || id.ValueString() != createdID {
		t.Fatal("known created identity lost")
	}
	var assignments types.Set
	if d := st.GetAttribute(ctx, path.Root("assignments"), &assignments); d.HasError() {
		t.Fatal(d)
	}
	if assignments.IsNull() {
		for _, field := range []string{"name", "description", "platforms", "settings"} {
			var value types.String
			if d := st.GetAttribute(ctx, path.Root(field), &value); d.HasError() {
				t.Fatal(d)
			}
			if !value.IsNull() {
				t.Fatalf("%s projected before complete readback", field)
			}
		}
		var technologies types.List
		var tags types.Set
		if d := st.GetAttribute(ctx, path.Root("technologies"), &technologies); d.HasError() {
			t.Fatal(d)
		}
		if d := st.GetAttribute(ctx, path.Root("role_scope_tag_ids"), &tags); d.HasError() {
			t.Fatal(d)
		}
		if !technologies.IsNull() || !tags.IsNull() {
			t.Fatal("planned collection fields projected before complete readback")
		}
		return
	}
	if assignments.IsUnknown() {
		t.Fatal("unknown assignment state returned after failed create")
	}
	// Complete state is legitimate only after all observation routes actually ran.
	if s.countRequests("GET", "/"+createdID) == 0 || s.countRequests("GET", "('"+createdID+"')/settings") == 0 {
		t.Fatal("full state projected without a complete remote read")
	}
	if s.countRequests("GET", "('"+createdID+"')/assignments") == 0 {
		t.Fatal("assignment state projected without an assignment read")
	}
	expected := cloneFixture(s.truth)
	expected.ID = createdID
	expected.Policy["id"] = createdID
	if !assignmentCommitted {
		expected.Assignments = []any{}
	}
	assertObserved(t, ctx, st, expected)
}

func TestEpochIncompleteReadDoesNotReplaceState(t *testing.T) {
	for _, fault := range []string{"wrong-read-id", "missing-assignment-page", "missing-settings-page", "base-get-400", "settings-get-400", "settings-get-404", "missing-name", "missing-platforms", "missing-technologies", "missing-isAssigned", "missing-settingCount", "wrong-isAssigned", "wrong-settingCount"} {
		t.Run(fault, func(t *testing.T) {
			ctx, r, s, st := setup(t)
			s.fault = fault
			out := resource.ReadResponse{State: st}
			r.Read(ctx, resource.ReadRequest{State: st}, &out)
			if !out.Diagnostics.HasError() {
				t.Fatal("incomplete read accepted")
			}
			if !out.State.Raw.Equal(st.Raw) {
				t.Fatal("incomplete read replaced prior evidence")
			}
			if s.writes != 0 {
				t.Fatal("read mutated service")
			}
		})
	}
}

func TestEpochLostCreateResponseIsNotRetried(t *testing.T) {
	ctx, r, s, st := setup(t)
	s.fault = "lost-create-response"
	out := resource.CreateResponse{State: tfsdk.State{Schema: st.Schema, Raw: tftypes.NewValue(st.Raw.Type(), nil)}}
	r.Create(ctx, resource.CreateRequest{Plan: createPlan(t, ctx, st)}, &out)
	if !out.Diagnostics.HasError() {
		t.Fatal("lost response reported success")
	}
	if s.writes != 1 {
		t.Fatal("blind mutation retry")
	}
	if !out.State.Raw.IsNull() {
		t.Fatal("unobserved identity projected after lost create response")
	}
}

func TestEpochCreateReadFailureRetainsOnlyKnownFacts(t *testing.T) {
	for _, fault := range []string{"wrong-read-id", "missing-assignment-page", "missing-settings-page", "base-get-400", "settings-get-400", "settings-get-404", "missing-name", "missing-platforms", "missing-technologies", "missing-isAssigned", "missing-settingCount", "wrong-isAssigned", "wrong-settingCount"} {
		t.Run(fault, func(t *testing.T) {
			ctx, r, s, st := setup(t)
			s.fault = fault
			out := resource.CreateResponse{State: tfsdk.State{Schema: st.Schema, Raw: tftypes.NewValue(st.Raw.Type(), nil)}}
			r.Create(ctx, resource.CreateRequest{Plan: createPlan(t, ctx, st)}, &out)
			if !out.Diagnostics.HasError() {
				t.Fatal("incomplete create observation accepted")
			}
			if s.writes != 2 || s.countRequests("POST", "/assign") != 1 {
				t.Fatal("mutation retried after incomplete readback")
			}
			var assignments types.Set
			if d := out.State.GetAttribute(ctx, path.Root("assignments"), &assignments); d.HasError() {
				t.Fatal(d)
			}
			if !assignments.IsNull() {
				t.Fatal("incomplete read projected planned assignments")
			}
			assertFailedCreateState(t, ctx, out.State, s, true)
		})
	}
}

func TestEpochLostAssignmentResponseRetainsIdentityWithoutRetry(t *testing.T) {
	ctx, r, s, st := setup(t)
	s.fault = "lost-assignment-response"
	out := resource.CreateResponse{State: tfsdk.State{Schema: st.Schema, Raw: tftypes.NewValue(st.Raw.Type(), nil)}}
	r.Create(ctx, resource.CreateRequest{Plan: createPlan(t, ctx, st)}, &out)
	if !out.Diagnostics.HasError() {
		t.Fatal("lost assignment response reported success")
	}
	if s.writes != 2 || s.countRequests("POST", "/assign") != 1 {
		t.Fatal("assignment mutation retried")
	}
	assertFailedCreateState(t, ctx, out.State, s, true)
}

func TestEpochCreateWithEmptyAssignments(t *testing.T) {
	for _, explicit := range []bool{false, true} {
		t.Run(fmt.Sprintf("explicit-empty-%v", explicit), func(t *testing.T) {
			ctx, r, s, st := setup(t)
			plan := createPlan(t, ctx, st)
			var assignments types.Set
			if d := st.GetAttribute(ctx, path.Root("assignments"), &assignments); d.HasError() {
				t.Fatal(d)
			}
			value := types.SetNull(assignments.ElementType(ctx))
			wantWrites := 1
			if explicit {
				value = types.SetValueMust(assignments.ElementType(ctx), nil)
				wantWrites = 2 // Explicit empty set is an intentional clearing assignment request.
			}
			if d := plan.SetAttribute(ctx, path.Root("assignments"), value); d.HasError() {
				t.Fatal(d)
			}
			out := resource.CreateResponse{State: tfsdk.State{Schema: st.Schema, Raw: tftypes.NewValue(st.Raw.Type(), nil)}}
			r.Create(ctx, resource.CreateRequest{Plan: plan}, &out)
			if out.Diagnostics.HasError() {
				t.Fatal(out.Diagnostics)
			}
			expected := cloneFixture(s.truth)
			expected.ID = createdID
			expected.Policy["id"] = createdID
			expected.Assignments = []any{}
			expected.UnmanagedEmptyAssignments = !explicit
			assertObserved(t, ctx, out.State, expected)
			if len(s.data.Assignments) != 0 {
				t.Fatal("new empty policy inherited assignments")
			}
			if s.writes != wantWrites || s.countRequests("POST", "/assign") != wantWrites-1 {
				t.Fatal("empty create dispatched unexpected assignments")
			}
		})
	}
}

func TestEpochReadAssignmentPageBoundaries(t *testing.T) {
	for _, count := range []int{0, 1, 2} {
		t.Run(fmt.Sprint(count), func(t *testing.T) {
			ctx, r, s, st := setup(t)
			expected := cloneFixture(s.truth)
			expected.Assignments = expected.Assignments[:count]
			s.data.Assignments = s.data.Assignments[:count]
			s.data.Policy["isAssigned"] = count > 0
			out := resource.ReadResponse{State: st}
			r.Read(ctx, resource.ReadRequest{State: st}, &out)
			if out.Diagnostics.HasError() {
				t.Fatal(out.Diagnostics)
			}
			assertObserved(t, ctx, out.State, expected)
			if s.writes != 0 {
				t.Fatal("read mutated remote policy")
			}
		})
	}
}

// Exercise the actual resource identity schema as framework callers do. The
// direct harness still does not claim RPC/core persistence or framework-owned
// identity removal after Delete.
func TestEpochResourceIdentityCreatePartialAndFullLifecycle(t *testing.T) {
	for _, fault := range []string{"", "assignment-denied", "lost-assignment-response", "missing-created-id"} {
		t.Run("fault-"+fault, func(t *testing.T) {
			ctx, r, s, st := setup(t)
			identitySchema := resource.IdentitySchemaResponse{}
			r.IdentitySchema(ctx, resource.IdentitySchemaRequest{}, &identitySchema)
			if identitySchema.Diagnostics.HasError() {
				t.Fatal(identitySchema.Diagnostics)
			}
			plannedIdentity := tfsdk.ResourceIdentity{Schema: identitySchema.IdentitySchema, Raw: tftypes.NewValue(identitySchema.IdentitySchema.Type().TerraformType(ctx), nil)}
			if d := plannedIdentity.SetAttribute(ctx, path.Root("id"), types.StringUnknown()); d.HasError() {
				t.Fatal(d)
			}
			responseIdentity := tfsdk.ResourceIdentity{Schema: plannedIdentity.Schema, Raw: plannedIdentity.Raw.Copy()}
			s.fault = fault
			out := resource.CreateResponse{State: tfsdk.State{Schema: st.Schema, Raw: tftypes.NewValue(st.Raw.Type(), nil)}, Identity: &responseIdentity}
			r.Create(ctx, resource.CreateRequest{Plan: createPlan(t, ctx, st), Identity: &plannedIdentity}, &out)
			if out.Diagnostics.HasError() != (fault != "") {
				t.Fatal("unexpected create diagnostic status")
			}
			var identityID types.String
			if d := out.Identity.GetAttribute(ctx, path.Root("id"), &identityID); d.HasError() {
				t.Fatal(d)
			}
			if fault == "missing-created-id" {
				if !identityID.IsNull() && !identityID.IsUnknown() {
					t.Fatal("unobserved identity fabricated")
				}
				if !out.State.Raw.IsNull() || s.writes != 1 || s.countRequests("POST", "/assign") != 0 {
					t.Fatal("unknown identity caused additional effects")
				}
				return
			}
			if identityID.IsUnknown() || identityID.IsNull() || identityID.ValueString() != createdID {
				t.Fatal("known resource identity lost before partial/full create returned")
			}
			var stateID types.String
			if d := out.State.GetAttribute(ctx, path.Root("id"), &stateID); d.HasError() {
				t.Fatal(d)
			}
			if stateID != identityID {
				t.Fatal("resource identity and state identity diverged")
			}
			// A separate authorized read reconciles the failed create; it does
			// not retry any mutation or synthesize management intent.
			s.fault = ""
			writesBefore := s.writes
			read := resource.ReadResponse{State: out.State, Identity: out.Identity}
			r.Read(ctx, resource.ReadRequest{State: out.State, Identity: out.Identity}, &read)
			if read.Diagnostics.HasError() || s.writes != writesBefore {
				t.Fatal("identity recovery read failed or mutated")
			}
			var readID types.String
			if d := read.Identity.GetAttribute(ctx, path.Root("id"), &readID); d.HasError() {
				t.Fatal(d)
			}
			if readID != identityID {
				t.Fatal("read changed immutable resource identity")
			}
			expected := cloneFixture(s.truth)
			expected.ID = createdID
			expected.Policy["id"] = createdID
			if fault == "assignment-denied" {
				expected.Assignments = []any{}
				expected.UnmanagedEmptyAssignments = true
			}
			assertObserved(t, ctx, read.State, expected)
			if fault != "" {
				return
			}
			plan := tfsdk.Plan{Schema: read.State.Schema, Raw: read.State.Raw.Copy()}
			if d := plan.SetAttribute(ctx, path.Root("name"), types.StringValue("Identity-preserving update")); d.HasError() {
				t.Fatal(d)
			}
			update := resource.UpdateResponse{State: read.State, Identity: read.Identity}
			r.Update(ctx, resource.UpdateRequest{State: read.State, Plan: plan, Identity: read.Identity}, &update)
			if update.Diagnostics.HasError() {
				t.Fatal(update.Diagnostics)
			}
			expected.Policy["name"] = "Identity-preserving update"
			assertObserved(t, ctx, update.State, expected)
			var updateID types.String
			if d := update.Identity.GetAttribute(ctx, path.Root("id"), &updateID); d.HasError() {
				t.Fatal(d)
			}
			if updateID != identityID {
				t.Fatal("update changed immutable resource identity")
			}
			deleted := resource.DeleteResponse{State: update.State, Identity: update.Identity}
			r.Delete(ctx, resource.DeleteRequest{State: update.State, Identity: update.Identity}, &deleted)
			if deleted.Diagnostics.HasError() || !deleted.State.Raw.IsNull() || !s.deleted || s.writes != 5 {
				t.Fatal("identity-bound lifecycle did not delete exact created resource")
			}
		})
	}
}

// A confirmed empty assignment observation does not erase configured management
// intent. Cover transitions independently of mutable service response fixtures.
func TestEpochUpdateAssignmentManagementIntent(t *testing.T) {
	for _, tc := range []struct {
		name           string
		beforeExplicit bool
		after          string
	}{
		{name: "null-to-explicit-empty", after: "empty"},
		{name: "null-to-nonempty", after: "nonempty"},
		{name: "explicit-empty-to-null", beforeExplicit: true, after: "null"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			ctx, r, s, st := setup(t)
			var configuredTargets types.Set
			if d := st.GetAttribute(ctx, path.Root("assignments"), &configuredTargets); d.HasError() {
				t.Fatal(d)
			}
			elementType := configuredTargets.ElementType(ctx)
			initial := types.SetNull(elementType)
			if tc.beforeExplicit {
				initial = types.SetValueMust(elementType, nil)
			}
			create := createPlan(t, ctx, st)
			if d := create.SetAttribute(ctx, path.Root("assignments"), initial); d.HasError() {
				t.Fatal(d)
			}
			created := resource.CreateResponse{State: tfsdk.State{Schema: st.Schema, Raw: tftypes.NewValue(st.Raw.Type(), nil)}}
			r.Create(ctx, resource.CreateRequest{Plan: create}, &created)
			if created.Diagnostics.HasError() {
				t.Fatal(created.Diagnostics)
			}
			expected := cloneFixture(s.truth)
			expected.ID = createdID
			expected.Policy["id"] = createdID
			expected.Assignments = []any{}
			expected.UnmanagedEmptyAssignments = !tc.beforeExplicit
			assertObserved(t, ctx, created.State, expected)

			plannedTargets := types.SetNull(elementType)
			switch tc.after {
			case "empty":
				plannedTargets = types.SetValueMust(elementType, nil)
			case "nonempty":
				plannedTargets = configuredTargets
				expected.Assignments = cloneFixture(s.truth).Assignments
			}
			expected.UnmanagedEmptyAssignments = tc.after == "null"
			plan := tfsdk.Plan{Schema: created.State.Schema, Raw: created.State.Raw.Copy()}
			if d := plan.SetAttribute(ctx, path.Root("assignments"), plannedTargets); d.HasError() {
				t.Fatal(d)
			}
			writesBefore, assignBefore := s.writes, s.countRequests("POST", "/assign")
			updated := resource.UpdateResponse{State: created.State}
			r.Update(ctx, resource.UpdateRequest{State: created.State, Plan: plan}, &updated)
			if updated.Diagnostics.HasError() {
				t.Fatal(updated.Diagnostics)
			}
			wantAssign := 1
			if tc.after == "null" {
				wantAssign = 0 // Omitted targeting does not authorize a clear request.
			}
			if s.writes-writesBefore != 1+wantAssign || s.countRequests("POST", "/assign")-assignBefore != wantAssign {
				t.Fatal("management-intent transition dispatched an unexpected assignment mutation")
			}
			if !reflect.DeepEqual(s.data.Settings, expected.Settings) || !reflect.DeepEqual(assignmentTuples(t, s.data.Assignments), assignmentTuples(t, expected.Assignments)) {
				t.Fatal("management-intent update altered independently expected settings/targeting")
			}
			assertObserved(t, ctx, updated.State, expected)
			var observedTargets types.Set
			if d := updated.State.GetAttribute(ctx, path.Root("assignments"), &observedTargets); d.HasError() {
				t.Fatal(d)
			}
			if !observedTargets.Equal(plannedTargets) {
				t.Fatal("known planned assignments and confirmed readback differ in null/empty/content semantics")
			}
			refresh := resource.ReadResponse{State: updated.State}
			r.Read(ctx, resource.ReadRequest{State: updated.State}, &refresh)
			if refresh.Diagnostics.HasError() || !refresh.State.Raw.Equal(updated.State.Raw) || s.writes-writesBefore != 1+wantAssign {
				t.Fatal("second read changed management intent or dispatched a mutation")
			}
		})
	}
}
