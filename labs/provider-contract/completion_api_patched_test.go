package contract

import (
	"context"
	"encoding/json"
	constructors "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/constructors/graph_beta/device_management"
	custom "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/custom_requests"
	model "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/shared_models/graph_beta/device_management"
	state "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/state/graph_beta/device_management"
	validate "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/validate/graph_beta/device_management"
	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/schema/validator"
	"github.com/hashicorp/terraform-plugin-framework/types"
	abs "github.com/microsoft/kiota-abstractions-go"
	graphmodels "github.com/microsoftgraph/msgraph-beta-sdk-go/models"
)

// These are the exact entrypoints called by the repaired selected resource.
func completionConstruct(ctx context.Context, input types.String) ([]graphmodels.DeviceManagementConfigurationSettingable, error) {
	return constructors.ConstructSettingsCatalogSettingsStrict(ctx, input)
}
func completionState(ctx context.Context, data *model.SettingsCatalogJsonResourceModel, raw []byte) error {
	return state.StateConfigurationPolicySettingsStrict(ctx, data, raw)
}
func completionValid(input string) bool {
	resp := validator.StringResponse{}
	validate.StrictSettingsCatalogJSONValidator().ValidateString(context.Background(), validator.StringRequest{Path: path.Root("settings"), ConfigValue: types.StringValue(input)}, &resp)
	return !resp.Diagnostics.HasError()
}

func completionFetch(ctx context.Context, adapter abs.RequestAdapter, cfg custom.GetRequestConfig) (json.RawMessage, error) {
	return custom.GetConfigurationPolicyCollection(ctx, adapter, cfg)
}
