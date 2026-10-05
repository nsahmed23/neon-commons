package contract

import (
	"context"
	"encoding/json"
	constructors "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/constructors/graph_beta/device_management"
	custom "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/custom_requests"
	model "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/shared_models/graph_beta/device_management"
	state "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/state/graph_beta/device_management"
	"github.com/hashicorp/terraform-plugin-framework/types"
	abs "github.com/microsoft/kiota-abstractions-go"
	graphmodels "github.com/microsoftgraph/msgraph-beta-sdk-go/models"
)

// These are the exact entrypoints called by the original selected resource.
func completionConstruct(ctx context.Context, input types.String) ([]graphmodels.DeviceManagementConfigurationSettingable, error) {
	return constructors.ConstructSettingsCatalogSettings(ctx, input), nil
}
func completionState(ctx context.Context, data *model.SettingsCatalogJsonResourceModel, raw []byte) error {
	state.StateConfigurationPolicySettings(ctx, data, raw)
	return nil
}
func completionValid(input string) bool { return valid(input) }

func completionFetch(ctx context.Context, adapter abs.RequestAdapter, cfg custom.GetRequestConfig) (json.RawMessage, error) {
	return custom.GetRequestByResourceId(ctx, adapter, cfg)
}
