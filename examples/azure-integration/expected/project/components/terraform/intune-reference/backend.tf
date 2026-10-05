# Synthetic existing-backend integration. Do not initialize during dossier review.
terraform {
  backend "azurerm" {
    storage_account_name = "iacstatereference"
    container_name       = "tfstate"
    key                  = "reference/intune.tfstate"
    resource_group_name  = "rg-iac-state-reference"
    tenant_id            = "11111111-1111-4111-8111-111111111111"
    subscription_id      = "88888888-8888-4888-8888-888888888888"
    client_id            = "99999999-9999-4999-8999-999999999999"
    use_oidc             = true
    use_azuread_auth      = true
    use_cli              = false
  }
}
