# Synthetic source-qualified reference only. No provider or tenant execution.
terraform {
  required_version = ">= 1.13.1, < 1.14.0"
  required_providers {
    microsoft365 = { source = "deploymenttheory/microsoft365", version = "1.0.0" }
  }
}
variable "live_qualification_ack" {
  type = bool
  default = false
  description = "Must remain false until independent qualification and approval."
}
variable "policies" {
  type = any
  description = "Authoritative desired policies keyed by import key; set in the stack file."
}
resource "microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json" "policy" {
  for_each           = var.policies
  name               = each.value.name
  description        = each.value.description
  platforms          = each.value.platforms
  technologies       = each.value.technologies
  role_scope_tag_ids = each.value.role_scope_tag_ids
  settings           = jsonencode(each.value.settings)
  assignments        = each.value.assignments
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = var.live_qualification_ack
      error_message = "Reference materials only: qualify provider, target and authorization before execution."
    }
  }
}
output "adoption_object_ids" {
  description = "Provider-returned policy IDs; not proof of endpoint success."
  value = { for k, v in microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json.policy : k => v.id }
}
