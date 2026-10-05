// Local MPL-2.0 provider repair candidate. See completion/NOTICE.md.
package settingsjson

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
)

// Decode preserves numbers, nulls and empty arrays and rejects ambiguous JSON.
// Error messages deliberately contain no source values.
func Decode(raw []byte) (any, error) {
	if len(raw) > 4*1024*1024 {
		return nil, fmt.Errorf("settings JSON exceeds byte limit")
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	nodes := 0
	v, e := decode(d, 0, &nodes)
	if e != nil {
		return nil, e
	}
	if _, e = d.Token(); e != io.EOF {
		return nil, fmt.Errorf("trailing JSON content")
	}
	return v, nil
}
func decode(d *json.Decoder, depth int, nodes *int) (any, error) {
	*nodes++
	if depth > 128 || *nodes > 100000 {
		return nil, fmt.Errorf("JSON structural limit exceeded")
	}
	t, e := d.Token()
	if e != nil {
		return nil, fmt.Errorf("invalid JSON")
	}
	switch t {
	case json.Delim('{'):
		obj := map[string]any{}
		for d.More() {
			k, e := d.Token()
			if e != nil {
				return nil, fmt.Errorf("invalid object")
			}
			key, ok := k.(string)
			if !ok {
				return nil, fmt.Errorf("invalid key")
			}
			if _, ok = obj[key]; ok {
				return nil, fmt.Errorf("duplicate object key")
			}
			v, e := decode(d, depth+1, nodes)
			if e != nil {
				return nil, e
			}
			obj[key] = v
		}
		if end, e := d.Token(); e != nil || end != json.Delim('}') {
			return nil, fmt.Errorf("invalid object end")
		}
		return obj, nil
	case json.Delim('['):
		values := make([]any, 0)
		for d.More() {
			v, e := decode(d, depth+1, nodes)
			if e != nil {
				return nil, e
			}
			values = append(values, v)
		}
		if end, e := d.Token(); e != nil || end != json.Delim(']') {
			return nil, fmt.Errorf("invalid array end")
		}
		return values, nil
	default:
		if _, ok := t.(json.Delim); ok {
			return nil, fmt.Errorf("unexpected delimiter")
		}
		return t, nil
	}
}

// Settings extracts the explicit settings boundary. No observation fields, IDs,
// array order, nulls or empty collections are normalized away.
func Settings(raw []byte, response bool) ([]map[string]any, error) {
	value, e := Decode(raw)
	if e != nil {
		return nil, e
	}
	obj, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("settings envelope must be an object")
	}
	key := "settings"
	if response {
		key = "value"
	}
	if _, bad := obj["error"]; bad {
		return nil, fmt.Errorf("settings error envelope")
	}
	if _, pending := obj["@odata.nextLink"]; pending {
		return nil, fmt.Errorf("incomplete settings response")
	}
	if !response && len(obj) != 1 {
		return nil, fmt.Errorf("configuration requires only settings boundary")
	}
	rows, ok := obj[key].([]any)
	if !ok {
		return nil, fmt.Errorf("settings boundary must be an array")
	}
	if len(rows) > 10000 {
		return nil, fmt.Errorf("setting count limit exceeded")
	}
	seen := map[string]bool{}
	result := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		item, ok := row.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("setting must be an object")
		}
		id, ok := item["id"].(string)
		if !ok || id == "" || seen[id] {
			return nil, fmt.Errorf("setting ID is missing or duplicated")
		}
		seen[id] = true
		instance, ok := item["settingInstance"].(map[string]any)
		if !ok {
			return nil, fmt.Errorf("setting instance must be an object")
		}
		if e := instanceValid(instance); e != nil {
			return nil, e
		}
		if e := typesValid(item); e != nil {
			return nil, e
		}
		result = append(result, item)
	}
	return result, nil
}
func instanceValid(obj map[string]any) error {
	typ, ok := obj["@odata.type"].(string)
	if !ok {
		return fmt.Errorf("setting instance discriminator required")
	}
	field := ""
	collection := false
	switch typ {
	case "#microsoft.graph.deviceManagementConfigurationSimpleSettingInstance":
		field = "simpleSettingValue"
	case "#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance":
		field = "choiceSettingValue"
	case "#microsoft.graph.deviceManagementConfigurationSimpleSettingCollectionInstance":
		field = "simpleSettingCollectionValue"
		collection = true
	case "#microsoft.graph.deviceManagementConfigurationChoiceSettingCollectionInstance":
		field = "choiceSettingCollectionValue"
		collection = true
	case "#microsoft.graph.deviceManagementConfigurationGroupSettingCollectionInstance":
		field = "groupSettingCollectionValue"
		collection = true
	default:
		return fmt.Errorf("unsupported setting instance type")
	}
	if id, ok := obj["settingDefinitionId"].(string); !ok || id == "" {
		return fmt.Errorf("setting definition ID required")
	}
	v, present := obj[field]
	if !present {
		return fmt.Errorf("setting value boundary required")
	}
	if collection {
		if v != nil {
			if _, ok := v.([]any); !ok {
				return fmt.Errorf("setting collection must be an array or null")
			}
		}
	} else {
		if _, ok := v.(map[string]any); !ok {
			return fmt.Errorf("setting value must be an object")
		}
	}
	return nil
}
func typesValid(value any) error {
	switch v := value.(type) {
	case map[string]any:
		if raw, exists := v["@odata.type"]; exists {
			typ, ok := raw.(string)
			if !ok {
				return fmt.Errorf("invalid discriminator")
			}
			switch typ {
			case "#microsoft.graph.deviceManagementConfigurationSetting",
				"#microsoft.graph.deviceManagementConfigurationChoiceSettingValue",
				"#microsoft.graph.deviceManagementConfigurationGroupSettingValue",
				"#microsoft.graph.deviceManagementConfigurationStringSettingValue",
				"#microsoft.graph.deviceManagementConfigurationIntegerSettingValue",
				"#microsoft.graph.deviceManagementConfigurationSettingInstanceTemplateReference",
				"#microsoft.graph.deviceManagementConfigurationSettingValueTemplateReference":
			case "#microsoft.graph.deviceManagementConfigurationSimpleSettingInstance",
				"#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance",
				"#microsoft.graph.deviceManagementConfigurationSimpleSettingCollectionInstance",
				"#microsoft.graph.deviceManagementConfigurationChoiceSettingCollectionInstance",
				"#microsoft.graph.deviceManagementConfigurationGroupSettingCollectionInstance":
				if e := instanceValid(v); e != nil {
					return e
				}
			default:
				return fmt.Errorf("unsupported polymorphic or secret setting type")
			}
		}
		if children, exists := v["children"]; exists && children != nil {
			rows, ok := children.([]any)
			if !ok {
				return fmt.Errorf("setting children must be an array or null")
			}
			for _, child := range rows {
				instance, ok := child.(map[string]any)
				if !ok {
					return fmt.Errorf("setting child must be an instance object")
				}
				if err := instanceValid(instance); err != nil {
					return err
				}
			}
		}
		for _, child := range v {
			if e := typesValid(child); e != nil {
				return e
			}
		}
	case []any:
		for _, child := range v {
			if e := typesValid(child); e != nil {
				return e
			}
		}
	}
	return nil
}
func Canonical(raw []byte) (string, error) {
	v, e := Decode(raw)
	if e != nil {
		return "", e
	}
	b, e := json.Marshal(v)
	return string(b), e
}
