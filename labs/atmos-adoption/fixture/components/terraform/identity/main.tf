terraform {
  required_version = "= 1.10.0"
}
variable "stage" {
  type = string
}
resource "terraform_data" "identity" {}
output "identity" {
  value = terraform_data.identity.id
}
