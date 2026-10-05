package contract

import (
	"bytes"
	"context"
	"encoding/json"
	model "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/common/shared_models/graph_beta/device_management"
	"github.com/hashicorp/terraform-plugin-framework/types"
	writer "github.com/microsoft/kiota-serialization-json-go"
	"reflect"
	"strings"
	"testing"
)

func TestCompletionConstructorExactJSON(t *testing.T) {
	input := strings.Replace(config, `"id":"0"`, `"id":"37","@odata.type":"#microsoft.graph.deviceManagementConfigurationSetting","observation":null`, 1)
	values, err := completionConstruct(context.Background(), types.StringValue(input))
	if err != nil {
		t.Fatal(err)
	}
	if len(values) != 1 {
		t.Fatalf("setting dropped: %d", len(values))
	}
	if values[0].GetId() == nil || *values[0].GetId() != "37" {
		t.Error("immutable source setting ID was dropped")
	}
	got := serialized(t, values[0])
	want := decode(t, input).(map[string]any)["settings"].([]any)[0]
	if !reflect.DeepEqual(got, want) {
		t.Errorf("serialized settings differ: got %v want %v", got, want)
	}
}
func TestCompletionUnknownNestedTypeRejectsWholePayload(t *testing.T) {
	obj := decode(t, config).(map[string]any)
	item := obj["settings"].([]any)[0].(map[string]any)
	inst := item["settingInstance"].(map[string]any)
	inst["choiceSettingValue"].(map[string]any)["children"] = []any{map[string]any{"@odata.type": "#future.type", "settingDefinitionId": "x"}}
	b, _ := json.Marshal(obj)
	if got, err := completionConstruct(context.Background(), types.StringValue(string(b))); err == nil || got != nil {
		t.Fatal("unsupported nested type returned successful partial settings")
	}
}
func TestCompletionStateRejectsMalformedAndErrorEnvelope(t *testing.T) {
	for _, input := range []string{`{`, `{"error":{"code":"AccessDenied"}}`, `{"value":null}`, `{"value":[{"id":"0","settingInstance":null}]}`} {
		m := model.SettingsCatalogJsonResourceModel{Settings: types.StringValue(config)}
		if err := completionState(context.Background(), &m, []byte(input)); err == nil {
			t.Errorf("invalid response reported successful observation for %s", input)
		}
		if !m.Settings.Equal(types.StringValue(config)) {
			t.Fatal("failed observation changed previously known state")
		}
	}
}
func TestCompletionValidatorPreservesObservedIDsAndWrappers(t *testing.T) {
	obj := decode(t, config).(map[string]any)
	first := obj["settings"].([]any)[0].(map[string]any)
	first["id"] = "37"
	first["@odata.type"] = "#microsoft.graph.deviceManagementConfigurationSetting"
	second := decode(t, config).(map[string]any)["settings"].([]any)[0].(map[string]any)
	second["id"] = "9"
	obj["settings"] = []any{first, second}
	b, _ := json.Marshal(obj)
	if !completionValid(string(b)) {
		t.Fatal("stable nonadjacent observed IDs and wrapper rejected")
	}
}
func TestCompletionDuplicateJSONKeysRejected(t *testing.T) {
	input := strings.Replace(config, `"id":"0"`, `"id":"0","id":"1"`, 1)
	if completionValid(input) {
		t.Fatal("ambiguous duplicate IDs accepted")
	}
}
func TestCompletionConstructorRejectsSecretRoundtrip(t *testing.T) {
	input := `{"settings":[{"id":"9","settingInstance":{"@odata.type":"#microsoft.graph.deviceManagementConfigurationSimpleSettingInstance","settingDefinitionId":"secret","simpleSettingValue":{"@odata.type":"#microsoft.graph.deviceManagementConfigurationSecretSettingValue","value":"synthetic-secret","valueState":"notEncrypted"}}}]}`
	if got, err := completionConstruct(context.Background(), types.StringValue(input)); err == nil || got != nil {
		t.Fatal("unqualified secret reconstruction admitted")
	}
}

func TestCompletionMissingNestedTypeRejectsWholePayload(t *testing.T) {
	input := strings.Replace(config, `"children":[]`, `"children":[{}]`, 1)
	if got, err := completionConstruct(context.Background(), types.StringValue(input)); err == nil || got != nil {
		t.Fatal("invalid nested instance returned partial settings")
	}
}

func TestCompletionExactNumberSurvivesSerialization(t *testing.T) {
	input := strings.Replace(config, `"id":"0"`, `"id":"0","observationNumber":9007199254740993`, 1)
	values, err := completionConstruct(context.Background(), types.StringValue(input))
	if err != nil {
		t.Fatal(err)
	}
	if len(values) != 1 {
		t.Fatal("setting dropped")
	}
	w := writer.NewJsonSerializationWriter()
	if err := w.WriteObjectValue("", values[0]); err != nil {
		t.Fatal(err)
	}
	raw, err := w.GetSerializedContent()
	if err != nil {
		t.Fatal(err)
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var got map[string]any
	if err := decoder.Decode(&got); err != nil {
		t.Fatal(err)
	}
	if got["observationNumber"] != json.Number("9007199254740993") {
		t.Fatal("number changed or observation dropped")
	}
}
