resource "aws_dynamodb_table" "todos" {
  name           = "${var.project}-todos-${var.stage}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "id"
  attribute {
    name = "id"
    type = "S"
  }
  ttl {
    attribute_name = "ttl"
    enabled        = false
  }
  tags = {
    Project = var.project
    Stage   = var.stage
  }
}

