terraform {
  required_version = "= 1.10.0"
}

variable "stage" {
  type = string
}
variable "setting" {
  type = string
}
variable "included_groups" {
  type = list(string)
}
variable "excluded_groups" {
  type = list(string)
}

# These built-in resources store only local values. They do not represent a
# service implementation of Intune policy updates or assignment replacement.
resource "terraform_data" "policy" {
  input = {
    name    = "adoption-lab-${var.stage}"
    setting = var.setting
  }
}

resource "terraform_data" "targeting" {
  input = {
    policy_id       = terraform_data.policy.id
    included_groups = var.included_groups
    excluded_groups = var.excluded_groups
  }
}

output "policy_id" {
  value = terraform_data.policy.id
}
output "targeting_id" {
  value = terraform_data.targeting.id
}
output "observed_setting" {
  value = terraform_data.policy.output.setting
}
