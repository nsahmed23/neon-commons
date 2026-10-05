package contract

import (
	"context"
	"encoding/json"
	constructors "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/constructors/graph_beta/device_management"
	"github.com/hashicorp/terraform-plugin-framework/types"
	serialization "github.com/microsoft/kiota-abstractions-go/serialization"
	writer "github.com/microsoft/kiota-serialization-json-go"
	sdk "github.com/microsoftgraph/msgraph-beta-sdk-go/models"
	"testing"
)

func serialized(t *testing.T, value serialization.Parsable) map[string]any {
	t.Helper()
	w := writer.NewJsonSerializationWriter()
	if e := w.WriteObjectValue("", value); e != nil {
		t.Fatal(e)
	}
	b, e := w.GetSerializedContent()
	if e != nil {
		t.Fatal(e)
	}
	var result map[string]any
	if e = json.Unmarshal(b, &result); e != nil {
		t.Fatal(e)
	}
	return result
}
func TestSDKSettingConstructorLeavesIDAndWrapperUnset(t *testing.T) {
	s := sdk.NewDeviceManagementConfigurationSetting()
	o := serialized(t, s)
	if _, ok := o["id"]; ok {
		t.Fatal(o)
	}
	if _, ok := o["@odata.type"]; ok {
		t.Fatal(o)
	}
}
func TestSDKSettingExplicitIDOdataAndAdditionalDataSurvive(t *testing.T) {
	s := sdk.NewDeviceManagementConfigurationSetting()
	id := "37"
	typ := "#microsoft.graph.deviceManagementConfigurationSetting"
	s.SetId(&id)
	s.SetOdataType(&typ)
	s.SetAdditionalData(map[string]any{"extra": "observed"})
	o := serialized(t, s)
	if o["id"] != id || o["@odata.type"] != typ || o["extra"] != "observed" {
		t.Fatal(o)
	}
}
func TestKnownHazardActualProviderConstructorDropsSettingID(t *testing.T) {
	values := constructors.ConstructSettingsCatalogSettings(context.Background(), types.StringValue(config))
	if len(values) != 1 {
		t.Fatal(len(values))
	}
	if values[0].GetId() != nil {
		t.Fatal("provider ID omission changed")
	}
	o := serialized(t, values[0])
	if _, ok := o["id"]; ok {
		t.Fatal(o)
	}
	t.Logf("request=%v", o)
}
func TestActualProviderOmitsNullTemplatesAndEmptyChildren(t *testing.T) {
	values := constructors.ConstructSettingsCatalogSettings(context.Background(), types.StringValue(config))
	o := serialized(t, values[0])
	i := o["settingInstance"].(map[string]any)
	v := i["choiceSettingValue"].(map[string]any)
	for _, check := range []struct {
		obj map[string]any
		key string
	}{{i, "settingInstanceTemplateReference"}, {v, "settingValueTemplateReference"}, {v, "children"}} {
		if _, ok := check.obj[check.key]; ok {
			t.Fatal(check)
		}
	}
	if v["@odata.type"] != "#microsoft.graph.deviceManagementConfigurationChoiceSettingValue" {
		t.Fatal(v)
	}
}
func TestSDKChoiceNilAndEmptyChildrenDiffer(t *testing.T) {
	s := sdk.NewDeviceManagementConfigurationChoiceSettingValue()
	a := serialized(t, s)
	s.SetChildren([]sdk.DeviceManagementConfigurationSettingInstanceable{})
	b := serialized(t, s)
	if _, ok := a["children"]; ok {
		t.Fatal(a)
	}
	if v, ok := b["children"].([]any); !ok || len(v) != 0 {
		t.Fatal(b)
	}
}
