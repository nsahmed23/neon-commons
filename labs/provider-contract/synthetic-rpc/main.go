// Test-only native RPC fixture provider. Never included in the production patch.
package main

import (
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"github.com/deploymenttheory/terraform-provider-microsoft365/internal/client"
	selected "github.com/deploymenttheory/terraform-provider-microsoft365/internal/services/resources/device_management/graph_beta/settings_catalog_configuration_policy_json"
	"github.com/hashicorp/terraform-plugin-framework/datasource"
	"github.com/hashicorp/terraform-plugin-framework/provider"
	"github.com/hashicorp/terraform-plugin-framework/provider/schema"
	"github.com/hashicorp/terraform-plugin-framework/providerserver"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	auth "github.com/microsoft/kiota-abstractions-go/authentication"
	httpadapter "github.com/microsoft/kiota-http-go"
	graph "github.com/microsoftgraph/msgraph-beta-sdk-go"
)

//go:embed fixture.json
var fixtureBytes []byte

type fixtureData struct {
	Policy      json.RawMessage   `json:"policy"`
	Settings    json.RawMessage   `json:"settings"`
	Assignments []json.RawMessage `json:"assignments"`
	ID          string            `json:"id"`
}
type transport struct {
	fixture     fixtureData
	emptyPolicy bool
}

func (t transport) RoundTrip(req *http.Request) (*http.Response, error) {
	file, err := os.OpenFile("fixture-requests.jsonl", os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
	if err != nil {
		return nil, err
	}
	row, _ := json.Marshal(map[string]string{"method": req.Method, "url": req.URL.String()})
	_, err = file.Write(append(row, '\n'))
	file.Close()
	if err != nil {
		return nil, err
	}
	if req.Method != "GET" || req.URL.Scheme != "https" || req.URL.Host != "graph.microsoft.com" {
		return nil, fmt.Errorf("fixture denies all non-GET or foreign requests")
	}
	root := "/beta/deviceManagement/configurationPolicies"
	id := t.fixture.ID
	body := []byte(nil)
	switch req.URL.Path {
	case root + "/" + id:
		body = t.fixture.Policy
		if t.emptyPolicy {
			body = nil
		}
	case root + "('" + id + "')/settings":
		if req.URL.Query().Get("$expand") != "children" {
			return nil, fmt.Errorf("fixture requires initial children expansion")
		}
		body = t.fixture.Settings
	case root + "('" + id + "')/assignments":
		token := req.URL.Query().Get("$skiptoken")
		if token == "" {
			body, _ = json.Marshal(map[string]any{"value": []json.RawMessage{t.fixture.Assignments[0]}, "@odata.nextLink": "https://graph.microsoft.com" + req.URL.Path + "?$skiptoken=fixture%2B2"})
		} else if token == "fixture+2" {
			body, _ = json.Marshal(map[string]any{"value": []json.RawMessage{t.fixture.Assignments[1]}})
		} else {
			return nil, fmt.Errorf("fixture rejects unknown continuation")
		}
	default:
		return nil, fmt.Errorf("fixture rejects unknown collection path")
	}
	return &http.Response{StatusCode: 200, ContentLength: int64(len(body)), Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(string(body))), Request: req}, nil
}

type fixtureProvider struct{}

func (*fixtureProvider) Metadata(ctx context.Context, req provider.MetadataRequest, resp *provider.MetadataResponse) {
	resp.TypeName = "microsoft365"
	resp.Version = "0.0.0-synthetic-resource-rpc"
}
func (*fixtureProvider) Schema(ctx context.Context, req provider.SchemaRequest, resp *provider.SchemaResponse) {
	resp.Schema = schema.Schema{Description: "Synthetic test-only provider; no authentication or live requests"}
}
func (*fixtureProvider) Resources(context.Context) []func() resource.Resource {
	return []func() resource.Resource{selected.NewSettingsCatalogJsonResource}
}
func (*fixtureProvider) DataSources(context.Context) []func() datasource.DataSource { return nil }
func (*fixtureProvider) Configure(ctx context.Context, req provider.ConfigureRequest, resp *provider.ConfigureResponse) {
	var fixture fixtureData
	if err := json.Unmarshal(fixtureBytes, &fixture); err != nil {
		resp.Diagnostics.AddError("fixture invalid", err.Error())
		return
	}
	httpClient := &http.Client{Transport: transport{fixture: fixture, emptyPolicy: os.Getenv("INTUNE_SYNTHETIC_EMPTY_POLICY") == "1"}, CheckRedirect: func(*http.Request, []*http.Request) error { return fmt.Errorf("fixture denies redirects") }}
	adapter, err := httpadapter.NewNetHttpRequestAdapterWithParseNodeFactoryAndSerializationWriterFactoryAndHttpClient(&auth.AnonymousAuthenticationProvider{}, nil, nil, httpClient)
	if err != nil {
		resp.Diagnostics.AddError("fixture adapter failed", err.Error())
		return
	}
	graphClient := graph.NewGraphServiceClient(adapter)
	resp.ResourceData = &client.GraphClients{KiotaGraphBetaClient: graphClient}
}
func main() {
	if err := providerserver.Serve(context.Background(), func() provider.Provider { return &fixtureProvider{} }, providerserver.ServeOpts{Address: "registry.terraform.io/deploymenttheory/microsoft365"}); err != nil {
		os.Exit(1)
	}
}
