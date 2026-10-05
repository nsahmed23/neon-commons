// Local MPL-2.0 provider repair candidate. See completion/NOTICE.md.
package devicemanagement

import (
	"context"
	"fmt"
	settingsjson "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/settingsjson"
	sharedmodels "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/shared_models/graph_beta/device_management"
	"github.com/hashicorp/terraform-plugin-framework/attr"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"strings"
)

// StateConfigurationPolicyAssignmentsStrict consumes a COMPLETE raw collection.
// Missing/denied/failed collections must never be supplied as empty desired sets.
func StateConfigurationPolicyAssignmentsStrict(ctx context.Context, data *sharedmodels.SettingsCatalogJsonResourceModel, raw []byte) error {
	value, e := settingsjson.Decode(raw)
	if e != nil {
		return e
	}
	envelope, ok := value.(map[string]any)
	if !ok {
		return fmt.Errorf("assignment envelope required")
	}
	if _, bad := envelope["error"]; bad {
		return fmt.Errorf("assignment error envelope")
	}
	if _, more := envelope["@odata.nextLink"]; more {
		return fmt.Errorf("assignment collection incomplete")
	}
	rows, ok := envelope["value"].([]any)
	if !ok {
		return fmt.Errorf("assignment collection must be an array")
	}
	typ := types.ObjectType{AttrTypes: map[string]attr.Type{"type": types.StringType, "group_id": types.StringType, "filter_id": types.StringType, "filter_type": types.StringType}}
	result := make([]attr.Value, 0, len(rows))
	seen := map[string]bool{}
	tuples := map[string]bool{}
	for _, rawRow := range rows {
		row, ok := rawRow.(map[string]any)
		if !ok {
			return fmt.Errorf("invalid assignment")
		}
		id, ok := row["id"].(string)
		if !ok || id == "" || seen[id] {
			return fmt.Errorf("assignment identity missing or duplicated")
		}
		seen[id] = true
		target, ok := row["target"].(map[string]any)
		if !ok {
			return fmt.Errorf("assignment target required")
		}
		for key := range target {
			switch key {
			case "@odata.type", "groupId", "deviceAndAppManagementAssignmentFilterId", "deviceAndAppManagementAssignmentFilterType":
			default:
				return fmt.Errorf("unsupported assignment target property")
			}
		}
		discriminator, ok := target["@odata.type"].(string)
		if !ok {
			return fmt.Errorf("assignment type required")
		}
		kind := strings.TrimPrefix(discriminator, "#microsoft.graph.")
		if discriminator != "#microsoft.graph."+kind {
			return fmt.Errorf("unsupported assignment discriminator")
		}
		obj := map[string]attr.Value{"type": types.StringValue(kind), "group_id": types.StringNull(), "filter_id": types.StringNull(), "filter_type": types.StringNull()}
		group, hasGroup := target["groupId"]
		switch kind {
		case "groupAssignmentTarget", "exclusionGroupAssignmentTarget":
			s, ok := group.(string)
			if !hasGroup || !ok || s == "" {
				return fmt.Errorf("group assignment identity required")
			}
			obj["group_id"] = types.StringValue(s)
		case "allDevicesAssignmentTarget", "allLicensedUsersAssignmentTarget":
			if hasGroup && group != nil {
				return fmt.Errorf("unexpected group identity")
			}
		default:
			return fmt.Errorf("unsupported assignment target")
		}
		for key, name := range map[string]string{"deviceAndAppManagementAssignmentFilterId": "filter_id", "deviceAndAppManagementAssignmentFilterType": "filter_type"} {
			if v, exists := target[key]; exists && v != nil {
				s, ok := v.(string)
				if !ok || s == "" {
					return fmt.Errorf("invalid assignment filter")
				}
				obj[name] = types.StringValue(s)
			}
		}
		mode := obj["filter_type"].(types.String)
		filter := obj["filter_id"].(types.String)
		if !mode.IsNull() {
			switch mode.ValueString() {
			case "none":
			case "include", "exclude":
				if filter.IsNull() || filter.ValueString() == "00000000-0000-0000-0000-000000000000" {
					return fmt.Errorf("assignment filter identity required")
				}
			default:
				return fmt.Errorf("unsupported assignment filter mode")
			}
		}
		// The current Terraform tuple cannot represent absent versus null.
		// Do not invent default zero/none values from absent observations.
		if _, exists := target["deviceAndAppManagementAssignmentFilterId"]; !exists {
			return fmt.Errorf("assignment filter ID observation omitted; unsupported profile")
		}
		if _, exists := target["deviceAndAppManagementAssignmentFilterType"]; !exists {
			return fmt.Errorf("assignment filter mode observation omitted; unsupported profile")
		}

		object, diags := types.ObjectValue(typ.AttrTypes, obj)
		if diags.HasError() {
			return fmt.Errorf("assignment state conversion failed")
		}
		key := object.String()
		if tuples[key] {
			return fmt.Errorf("distinct assignment identities collapse to the same state tuple")
		}
		tuples[key] = true
		result = append(result, object)
	}
	// Preserve omitted configuration as unmanaged when service confirms no rows.
	// Explicit empty configuration remains an explicit empty set.
	if len(rows) == 0 && data.Assignments.IsNull() {
		return nil
	}
	set, diags := types.SetValue(typ, result)
	if diags.HasError() {
		return fmt.Errorf("assignment state set failed")
	}
	data.Assignments = set
	return nil
}
