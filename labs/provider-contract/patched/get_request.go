package customrequests

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	abstractions "github.com/microsoft/kiota-abstractions-go"
	s "github.com/microsoft/kiota-abstractions-go/serialization"
)

// GetRequestConfig contains the configuration for a custom GET request
type GetRequestConfig struct {
	// The API version to use (beta or v1.0)
	APIVersion GraphAPIVersion
	// The base endpoint (e.g., "deviceManagement/configurationPolicies")
	Endpoint string
	// The endpoint suffix appended after the ID (e.g., "/settings"). Optional.
	EndpointSuffix string
	// The resource ID syntax format (e.g., "('id')" or "(id)")
	ResourceIDPattern string
	// The ID of the resource
	ResourceID string
	// Optional query parameters to include in the request
	QueryParameters map[string]string
}

// ODataResponse represents the structure of an OData response
type ODataResponse struct {
	// Value is the array of JSON messages returned by the request
	Value []json.RawMessage `json:"value"`
	//  NextLink is the URL for the next page of results used by pagination
	NextLink string `json:"@odata.nextLink,omitempty"`
}

func GetRequest(
	ctx context.Context,
	adapter abstractions.RequestAdapter,
	config GetRequestConfig,
	factory s.ParsableFactory,
	errorMappings abstractions.ErrorMappings,
) (s.Parsable, error) {
	requestInfo := abstractions.NewRequestInformation()
	requestInfo.Method = abstractions.GET
	requestInfo.UrlTemplate = "{+baseurl}/" + config.Endpoint
	if config.GetResourceID() != "" {
		requestInfo.UrlTemplate += "/" + config.GetResourceID()
	}
	if config.GetEndpointSuffix() != "" {
		requestInfo.UrlTemplate += "/" + config.GetEndpointSuffix()
	}

	requestInfo.PathParameters = map[string]string{
		"baseurl": fmt.Sprintf("https://graph.microsoft.com/%s", config.APIVersion),
	}

	if config.QueryParameters != nil {
		for key, value := range config.QueryParameters {
			requestInfo.QueryParameters[key] = value
		}
	}

	result, err := adapter.Send(ctx, requestInfo, factory, errorMappings)
	if err != nil {
		return nil, err
	}

	return result, nil
}

// GetRequestByResourceId performs a custom GET request using the Microsoft Graph SDK when the operation
// is not available in the generated SDK methods or when using raw json is easier to handle for response handling.
// This function supports both Beta and V1.0 Graph API versions and automatically handles OData pagination if present.
//
// e.g., GET https://graph.microsoft.com/beta/deviceManagement/configurationPolicies('191056b1-4c4a-4871-8518-162a105d011a')/settings
//
// The function handles:
// - Construction of the Graph API URL with proper formatting
// - Setting up the GET request with optional query parameters
// - Sending the request with proper authentication
// - Automatic pagination if the response is an OData response with a nextLink
// - Combining paginated results into a single response
// - Returning the raw JSON response
//
// Parameters:
//   - ctx: The context for the request, which can be used for cancellation and timeout
//   - adapter: The request adapter for sending the request
//   - config: GetRequestConfig containing:
//   - APIVersion: The Graph API version to use (Beta or V1.0)
//   - Endpoint: The resource endpoint path (e.g., "/deviceManagement/configurationPolicies")
//   - ResourceID: The ID of the resource to retrieve
//   - ResourceIDPattern: The format for the resource ID (e.g., "('id')" or "(id)")
//   - EndpointSuffix: Optional suffix to append after the resource ID (e.g., "/settings")
//   - QueryParameters: Optional query parameters for the request
//
// Returns:
//   - json.RawMessage: The raw JSON response from the GET request. For paginated responses,
//     returns a combined response with all results in the "value" array
//   - error: Returns nil if the request was successful, otherwise an error describing what went wrong
//
// Example Usage:
//
//	config := GetRequestConfig{
//		APIVersion:        GraphAPIBeta,
//		Endpoint:         "/deviceManagement/configurationPolicies",
//		ResourceID:       "d557c813-b8e5-4efc-b00e-9c0bd5fd10df",
//		ResourceIDPattern: "('id')",
//		EndpointSuffix:   "/settings",
//		QueryParameters: map[string]string{
//			"$expand": "children",
//		},
//	}
//
//	response, err := GetRequestByResourceId(ctx, adapter, config)
//	if err != nil {
//		log.Fatalf("Error: %v", err)
//	}
//
//	fmt.Printf("Response: %+v\n", response)
//
// These limits are conservative local support limits, not Graph service limits.
const maxCustomRequestBodyBytes int64 = 4 * 1024 * 1024
const maxCustomCollectionBytes = 32 * 1024 * 1024
const maxCustomCollectionPages = 128

func GetRequestByResourceId(ctx context.Context, adapter abstractions.RequestAdapter, reqConfig GetRequestConfig) (json.RawMessage, error) {
	requestInfo := abstractions.NewRequestInformation()
	requestInfo.Method = abstractions.GET
	requestInfo.UrlTemplate = ByIDRequestUrlTemplate(reqConfig)
	requestInfo.PathParameters = map[string]string{
		"baseurl": fmt.Sprintf("https://graph.microsoft.com/%s", reqConfig.APIVersion),
	}
	root, err := requestInfo.GetUri()
	if err != nil || root.Scheme != "https" || root.Host != "graph.microsoft.com" || root.User != nil || root.Fragment != "" {
		return nil, fmt.Errorf("invalid initial custom Graph request URL")
	}
	// The old URL template had no query expansion. Set the initial URI explicitly.
	query := root.Query()
	for key, value := range reqConfig.QueryParameters {
		query.Set(key, value)
	}
	root.RawQuery = query.Encode()
	requestInfo.SetUri(*root)
	requestInfo.Headers.Add("Accept", "application/json")

	expectedCollection := reqConfig.EndpointSuffix == "/settings" || reqConfig.EndpointSuffix == "/assignments"
	visited := map[string]bool{root.String(): true}
	allResults := make([]json.RawMessage, 0)
	totalBytes := 0
	for pageNumber := 1; pageNumber <= maxCustomCollectionPages; pageNumber++ {
		body, err := makeRequest(ctx, adapter, requestInfo)
		if err != nil {
			return nil, err
		}
		totalBytes += len(body)
		if totalBytes > maxCustomCollectionBytes {
			return nil, fmt.Errorf("custom Graph collection exceeds byte limit")
		}
		object, err := decodeUniqueObject(body)
		if err != nil {
			return nil, fmt.Errorf("custom Graph response must be a JSON object")
		}
		if _, exists := object["error"]; exists {
			return nil, fmt.Errorf("custom Graph response contains an error object")
		}
		value, hasValue := object["value"]
		next, hasNext := object["@odata.nextLink"]
		if !hasValue {
			if expectedCollection || hasNext || pageNumber > 1 {
				return nil, fmt.Errorf("custom Graph collection page is missing value")
			}
			return body, nil // Preserve the helper's non-collection object support.
		}
		expectedCollection = true
		var items []json.RawMessage
		if err := json.Unmarshal(value, &items); err != nil || items == nil {
			return nil, fmt.Errorf("custom Graph collection value must be an array")
		}
		allResults = append(allResults, items...)
		nextLink := ""
		if hasNext {
			if strings.TrimSpace(string(next)) == "null" {
				return nil, fmt.Errorf("custom Graph continuation must be a string")
			}
			if err := json.Unmarshal(next, &nextLink); err != nil {
				return nil, fmt.Errorf("custom Graph continuation must be a string")
			}
		}
		if nextLink == "" {
			return json.Marshal(map[string]any{"value": allResults})
		}
		if pageNumber == maxCustomCollectionPages {
			return nil, fmt.Errorf("custom Graph collection exceeds page limit")
		}
		continuation, err := url.Parse(nextLink)
		if err != nil || continuation.Scheme != root.Scheme || continuation.Host != root.Host || continuation.User != nil || continuation.Fragment != "" || continuation.EscapedPath() != root.EscapedPath() {
			return nil, fmt.Errorf("custom Graph continuation is outside admitted collection")
		}
		if visited[nextLink] {
			return nil, fmt.Errorf("custom Graph continuation loop")
		}
		visited[nextLink] = true
		requestInfo = abstractions.NewRequestInformation()
		requestInfo.Method = abstractions.GET
		requestInfo.SetUri(*continuation) // Keep the complete returned query, byte for byte.
		requestInfo.Headers.Add("Accept", "application/json")
	}
	return nil, fmt.Errorf("custom Graph page limit reached")
}

// decodeUniqueObject rejects ambiguous duplicate envelope keys and trailing JSON.
func decodeUniqueObject(body []byte) (map[string]json.RawMessage, error) {
	decoder := json.NewDecoder(bytes.NewReader(body))
	token, err := decoder.Token()
	if err != nil || token != json.Delim('{') {
		return nil, fmt.Errorf("expected JSON object")
	}
	object := make(map[string]json.RawMessage)
	for decoder.More() {
		keyToken, err := decoder.Token()
		if err != nil {
			return nil, err
		}
		key, ok := keyToken.(string)
		if !ok {
			return nil, fmt.Errorf("invalid JSON object key")
		}
		if _, duplicate := object[key]; duplicate {
			return nil, fmt.Errorf("duplicate JSON object key")
		}
		var value json.RawMessage
		if err := decoder.Decode(&value); err != nil {
			return nil, err
		}
		object[key] = value
	}
	if _, err := decoder.Token(); err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); err != io.EOF {
		return nil, fmt.Errorf("trailing JSON content")
	}
	return object, nil
}

// makeRequest executes an HTTP request using the provided Kiota request adapter and request information.
// This helper function handles the conversion of Kiota's RequestInformation into a native HTTP request,
// executes the request, and returns the raw response body.
//
// Parameters:
//   - ctx: The context for the request, which can be used for cancellation and timeout
//   - adapter: The Kiota request adapter that converts RequestInformation to a native request
//   - requestInfo: The Kiota RequestInformation containing the request configuration
//
// Returns:
//   - []byte: The raw response body from the HTTP request
//   - error: Returns nil if the request was successful, otherwise an error describing what went wrong
//
// The function performs the following steps:
// 1. Converts the Kiota RequestInformation to a native HTTP request
// 2. Executes the HTTP request using a standard http.Client
// 3. Reads and returns the complete response body
func makeRequest(ctx context.Context, adapter abstractions.RequestAdapter, requestInfo *abstractions.RequestInformation) ([]byte, error) {
	nativeReq, err := adapter.ConvertToNativeRequest(ctx, requestInfo)
	if err != nil {
		return nil, fmt.Errorf("custom Graph request conversion failed")
	}
	httpReq, ok := nativeReq.(*http.Request)
	if !ok || httpReq == nil {
		return nil, fmt.Errorf("custom Graph adapter returned invalid request")
	}
	client := &http.Client{
		Timeout: 30 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return fmt.Errorf("custom Graph redirects are not admitted")
		},
	}
	resp, err := client.Do(httpReq)
	if err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, fmt.Errorf("custom Graph transport failed; remote outcome unknown")
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("custom Graph HTTP status %d", resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, maxCustomRequestBodyBytes+1))
	if err != nil {
		return nil, fmt.Errorf("custom Graph response body read failed")
	}
	if int64(len(body)) > maxCustomRequestBodyBytes {
		return nil, fmt.Errorf("custom Graph response exceeds byte limit")
	}
	return body, nil
}
