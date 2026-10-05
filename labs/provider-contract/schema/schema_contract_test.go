package contract

import (
	"context"
	"github.com/hashicorp/terraform-plugin-framework/attr"
	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/defaults"
	"github.com/hashicorp/terraform-plugin-framework/schema/validator"
	"github.com/hashicorp/terraform-plugin-framework/tfsdk"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"strings"
	"testing"
)

func selectedSchema(t *testing.T) schema.Schema {
	t.Helper()
	r := resource.SchemaResponse{}
	(&SettingsCatalogJsonResource{}).Schema(context.Background(), resource.SchemaRequest{}, &r)
	if r.Diagnostics.HasError() {
		t.Fatal(r.Diagnostics)
	}
	return r.Schema
}
func TestSchemaFrameworkImplementationValidation(t *testing.T) {
	s := selectedSchema(t)
	if d := s.ValidateImplementation(context.Background()); d.HasError() {
		t.Fatal(d)
	}
}
func TestSchemaRequiredAndComputedFieldContracts(t *testing.T) {
	s := selectedSchema(t)
	if !s.Attributes["id"].IsComputed() || s.Attributes["id"].IsRequired() {
		t.Fatal("ID contract")
	}
	for _, name := range []string{"name", "settings"} {
		if !s.Attributes[name].IsRequired() {
			t.Fatal(name)
		}
	}
	a, ok := s.Attributes["assignments"].(schema.SetNestedAttribute)
	if !ok || !a.Optional {
		t.Fatal("assignment set contract")
	}
	if _, ok := a.NestedObject.Attributes["filter_id"]; !ok {
		t.Fatal("filter missing")
	}
}
func TestSchemaSelectedSettingsValidatorsAcceptBoundedCandidate(t *testing.T) {
	s := selectedSchema(t).Attributes["settings"].(schema.StringAttribute)
	for _, v := range s.Validators {
		r := validator.StringResponse{}
		v.ValidateString(context.Background(), validator.StringRequest{Path: path.Root("settings"), ConfigValue: types.StringValue(config)}, &r)
		if r.Diagnostics.HasError() {
			t.Fatal(r.Diagnostics)
		}
	}
}
func TestSchemaDescriptionLengthLimit(t *testing.T) {
	s := selectedSchema(t).Attributes["description"].(schema.StringAttribute)
	for _, count := range []int{1500, 1501} {
		r := validator.StringResponse{}
		for _, v := range s.Validators {
			v.ValidateString(context.Background(), validator.StringRequest{Path: path.Root("description"), ConfigValue: types.StringValue(strings.Repeat("x", count))}, &r)
		}
		if r.Diagnostics.HasError() != (count == 1501) {
			t.Fatal(count, r.Diagnostics)
		}
	}
}
func assignmentConfig(t *testing.T, filterID types.String, filterType string) tfsdk.Config {
	t.Helper()
	attrs := map[string]attr.Type{"filter_id": types.StringType, "filter_type": types.StringType}
	obj, d := types.ObjectValue(attrs, map[string]attr.Value{"filter_id": filterID, "filter_type": types.StringValue(filterType)})
	if d.HasError() {
		t.Fatal(d)
	}
	raw, e := obj.ToTerraformValue(context.Background())
	if e != nil {
		t.Fatal(e)
	}
	return tfsdk.Config{Raw: raw, Schema: schema.Schema{Attributes: map[string]schema.Attribute{"filter_id": schema.StringAttribute{Optional: true}, "filter_type": schema.StringAttribute{Optional: true}}}}
}
func TestSchemaFilterDefaultAndExplicitZeroAreDistinct(t *testing.T) {
	a := selectedSchema(t).Attributes["assignments"].(schema.SetNestedAttribute).NestedObject.Attributes["filter_id"].(schema.StringAttribute)
	r := defaults.StringResponse{}
	a.Default.DefaultString(context.Background(), defaults.StringRequest{Path: path.Root("filter_id")}, &r)
	if r.Diagnostics.HasError() || r.PlanValue.ValueString() != "00000000-0000-0000-0000-000000000000" {
		t.Fatal(r)
	}
	result := validator.StringResponse{}
	for _, v := range a.Validators {
		v.ValidateString(context.Background(), validator.StringRequest{Path: path.Root("filter_id"), ConfigValue: r.PlanValue, Config: assignmentConfig(t, r.PlanValue, "none")}, &result)
	}
	if !result.Diagnostics.HasError() {
		t.Fatal("explicit zero unexpectedly accepted")
	}
}
func TestSchemaFilterIncludeRequiresID(t *testing.T) {
	a := selectedSchema(t).Attributes["assignments"].(schema.SetNestedAttribute).NestedObject.Attributes["filter_id"].(schema.StringAttribute)
	for _, mode := range []string{"include", "exclude", "none"} {
		r := validator.StringResponse{}
		for _, v := range a.Validators {
			v.ValidateString(context.Background(), validator.StringRequest{Path: path.Root("filter_id"), ConfigValue: types.StringNull(), Config: assignmentConfig(t, types.StringNull(), mode)}, &r)
		}
		if r.Diagnostics.HasError() != (mode != "none") {
			t.Fatal(mode, r.Diagnostics)
		}
	}
}
