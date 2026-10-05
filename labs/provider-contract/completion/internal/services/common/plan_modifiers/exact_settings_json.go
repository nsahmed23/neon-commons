// Local MPL-2.0 provider repair candidate. See completion/NOTICE.md.
package planmodifiers

import (
	"context"
	settingsjson "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/settingsjson"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
)

type ExactSettingsJSONPlanModifier struct{}

func (ExactSettingsJSONPlanModifier) Description(context.Context) string {
	return "Preserves JSON values, IDs, nulls and array order; canonicalizes object keys only."
}
func (m ExactSettingsJSONPlanModifier) MarkdownDescription(ctx context.Context) string {
	return m.Description(ctx)
}
func (ExactSettingsJSONPlanModifier) PlanModifyString(ctx context.Context, req planmodifier.StringRequest, resp *planmodifier.StringResponse) {
	if req.ConfigValue.IsNull() || req.ConfigValue.IsUnknown() {
		return
	}
	value, err := settingsjson.Canonical([]byte(req.ConfigValue.ValueString()))
	if err != nil {
		resp.Diagnostics.AddError("Invalid settings JSON", err.Error())
		return
	}
	resp.PlanValue = types.StringValue(value)
}
