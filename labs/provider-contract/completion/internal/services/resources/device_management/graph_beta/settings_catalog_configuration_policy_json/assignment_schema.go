package graphBetaSettingsCatalogConfigurationPolicyJson

import (
	"context"
	"regexp"

	"github.com/deploymenttheory/terraform-provider-microsoft365/internal/constants"
	commonschemagraphbeta "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/schema/graph_beta/device_management"
	"github.com/hashicorp/terraform-plugin-framework-validators/stringvalidator"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/schema/validator"
	"github.com/hashicorp/terraform-plugin-framework/types"
)

// Override only this resource's filter validation. The shared schema and its
// other callers retain their existing behavior and defaults.
func selectedAssignmentsSchema() schema.SetNestedAttribute {
	result := commonschemagraphbeta.DeviceConfigurationWithAllGroupAssignmentsAndFilterSchema()
	filter := result.NestedObject.Attributes["filter_id"].(schema.StringAttribute)
	filter.MarkdownDescription = "Filter identity. Include/exclude requires a non-zero GUID. An explicit zero GUID is supported only with none (also the default mode)."
	filter.Validators = []validator.String{
		stringvalidator.RegexMatches(regexp.MustCompile(constants.GuidRegex), "must be a valid GUID"),
		selectedFilterIdentityValidator{},
	}
	result.NestedObject.Attributes["filter_id"] = filter
	return result
}

type selectedFilterIdentityValidator struct{}

func (selectedFilterIdentityValidator) Description(context.Context) string {
	return "include/exclude requires an actual filter identity; zero is valid only with none"
}
func (v selectedFilterIdentityValidator) MarkdownDescription(ctx context.Context) string {
	return v.Description(ctx)
}
func (selectedFilterIdentityValidator) ValidateString(ctx context.Context, req validator.StringRequest, resp *validator.StringResponse) {
	if req.ConfigValue.IsUnknown() {
		return
	}
	var mode types.String
	resp.Diagnostics.Append(req.Config.GetAttribute(ctx, req.Path.ParentPath().AtName("filter_type"), &mode)...)
	if resp.Diagnostics.HasError() || mode.IsUnknown() {
		return
	}
	value := req.ConfigValue.ValueString()
	if mode.ValueString() == "include" || mode.ValueString() == "exclude" {
		if req.ConfigValue.IsNull() || value == "" || value == "00000000-0000-0000-0000-000000000000" {
			resp.Diagnostics.AddAttributeError(req.Path, "Filter Identity Required", "Include/exclude requires an explicit non-zero filter GUID.")
		}
		return
	}
	// A null configuration mode receives the existing explicit none default.
	if value == "00000000-0000-0000-0000-000000000000" && !mode.IsNull() && mode.ValueString() != "none" {
		resp.Diagnostics.AddAttributeError(req.Path, "Invalid Zero Filter", "The zero filter GUID is only valid with filter_type none.")
	}
}
