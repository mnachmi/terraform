variable "config_file" {
  description = "Path to the JSON configuration file"
  type        = string
  default     = "config.json"
}

locals {
  config = jsondecode(file(var.config_file))
}
