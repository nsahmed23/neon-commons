package contract

import (
	"context"
	model "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/shared_models/graph_beta/device_management"
	state "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/state/graph_beta/device_management"
	"github.com/hashicorp/terraform-plugin-framework/attr"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"testing"
)

func assignmentType() types.ObjectType {
	return types.ObjectType{AttrTypes: map[string]attr.Type{"type": types.StringType, "group_id": types.StringType, "filter_id": types.StringType, "filter_type": types.StringType}}
}
func TestCompletionAssignmentStateInclusionExclusionFilters(t *testing.T) {
	raw := `{"value":[{"id":"include","target":{"@odata.type":"#microsoft.graph.groupAssignmentTarget","groupId":"group-a","deviceAndAppManagementAssignmentFilterId":"filter-a","deviceAndAppManagementAssignmentFilterType":"include"}},{"id":"exclude","target":{"@odata.type":"#microsoft.graph.exclusionGroupAssignmentTarget","groupId":"group-b","deviceAndAppManagementAssignmentFilterId":null,"deviceAndAppManagementAssignmentFilterType":null}}]}`
	data := model.SettingsCatalogJsonResourceModel{Assignments: types.SetNull(assignmentType())}
	if e := state.StateConfigurationPolicyAssignmentsStrict(context.Background(), &data, []byte(raw)); e != nil {
		t.Fatal(e)
	}
	if len(data.Assignments.Elements()) != 2 {
		t.Fatal(data.Assignments)
	}
	first := data.Assignments.Elements()[0].(types.Object).Attributes()
	second := data.Assignments.Elements()[1].(types.Object).Attributes()
	if first["type"] != types.StringValue("groupAssignmentTarget") || first["group_id"] != types.StringValue("group-a") || first["filter_id"] != types.StringValue("filter-a") || first["filter_type"] != types.StringValue("include") {
		t.Fatal(first)
	}
	if second["type"] != types.StringValue("exclusionGroupAssignmentTarget") || second["group_id"] != types.StringValue("group-b") || !second["filter_id"].IsNull() || !second["filter_type"].IsNull() {
		t.Fatal(second)
	}
}
func TestCompletionAssignmentStateEmptyVersusUnavailable(t *testing.T) {
	for _, invalid := range []string{`{}`, `{"value":null}`, `{"error":{}}`, `{"value":[],"@odata.nextLink":"next"}`, `{"value":[{"id":"a","target":{"@odata.type":"#future"}}]}`, `{"value":[{"id":"a","target":{"@odata.type":"#microsoft.graph.groupAssignmentTarget"}}]}`} {
		before := types.SetValueMust(assignmentType(), []attr.Value{})
		data := model.SettingsCatalogJsonResourceModel{Assignments: before}
		if e := state.StateConfigurationPolicyAssignmentsStrict(context.Background(), &data, []byte(invalid)); e == nil {
			t.Fatalf("invalid observation accepted: %s", invalid)
		}
		if !data.Assignments.Equal(before) {
			t.Fatal("state mutated before complete validation")
		}
	}
	for _, before := range []types.Set{types.SetNull(assignmentType()), types.SetValueMust(assignmentType(), []attr.Value{})} {
		data := model.SettingsCatalogJsonResourceModel{Assignments: before}
		if e := state.StateConfigurationPolicyAssignmentsStrict(context.Background(), &data, []byte(`{"value":[]}`)); e != nil {
			t.Fatal(e)
		}
		if !data.Assignments.Equal(before) {
			t.Fatal("omitted and empty collapsed")
		}
	}
}
func TestCompletionAssignmentStateRejectsTupleCollapse(t *testing.T) {
	raw := `{"value":[{"id":"a","target":{"@odata.type":"#microsoft.graph.allDevicesAssignmentTarget","deviceAndAppManagementAssignmentFilterId":null,"deviceAndAppManagementAssignmentFilterType":null}},{"id":"b","target":{"@odata.type":"#microsoft.graph.allDevicesAssignmentTarget","deviceAndAppManagementAssignmentFilterId":null,"deviceAndAppManagementAssignmentFilterType":null}}]}`
	data := model.SettingsCatalogJsonResourceModel{Assignments: types.SetNull(assignmentType())}
	if e := state.StateConfigurationPolicyAssignmentsStrict(context.Background(), &data, []byte(raw)); e == nil {
		t.Fatal("duplicate tuple silently collapsed")
	}
}
