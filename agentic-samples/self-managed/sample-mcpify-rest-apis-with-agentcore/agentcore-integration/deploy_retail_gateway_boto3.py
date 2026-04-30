#!/usr/bin/env python3
"""
Deployment script using raw boto3 client for AgentCore Gateway
Based on the proper boto3 patterns from AWS documentation
"""

import boto3
import json
import time
import random
import string
from datetime import datetime
from pprint import pprint

class RetailGatewayDeployerBoto3:
    def __init__(self, region='us-east-1'):
        self.region = region
        self.agentcore_client = boto3.client('bedrock-agentcore-control', region_name=region)
        self.cognito_client = boto3.client('cognito-idp', region_name=region)
        self.iam_client = boto3.client('iam', region_name=region)
        
        # Generate unique identifiers
        self.unique_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))  # nosec B311 - Used for resource naming, not cryptographic purposes
        self.timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        
    def generate_openapi_spec(self, api_base_url="https://api.yourcompany.com"):
        """Generate the OpenAPI specification for the retail API"""
        return {
            "openapi": "3.0.0",
            "info": {
                "title": "Retail Demo API",
                "description": "Comprehensive retail management API with orders, products, customers, and analytics",
                "version": "1.0.0"
            },
            "servers": [
                {
                    "url": api_base_url,
                    "description": "EKS Retail API Server"
                }
            ],
            "paths": {
                "/health": {
                    "get": {
                        "operationId": "checkHealth",
                        "summary": "Health check endpoint",
                        "description": "Check if the retail API service is healthy",
                        "responses": {
                            "200": {
                                "description": "Service is healthy",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "status": {"type": "string", "example": "healthy"},
                                                "timestamp": {"type": "string", "format": "date-time"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/orders": {
                    "get": {
                        "operationId": "listOrders",
                        "summary": "List all orders",
                        "description": "Retrieve a list of all orders in the system",
                        "responses": {
                            "200": {
                                "description": "List of orders",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "orders": {
                                                    "type": "array",
                                                    "items": {"$ref": "#/components/schemas/Order"}
                                                },
                                                "count": {"type": "integer"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/order/{orderId}": {
                    "get": {
                        "operationId": "getOrder",
                        "summary": "Get specific order",
                        "description": "Retrieve details of a specific order by ID",
                        "parameters": [
                            {
                                "name": "orderId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                                "description": "The order ID"
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "Order details",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Order"}
                                    }
                                }
                            },
                            "404": {"description": "Order not found"}
                        }
                    },
                    "put": {
                        "operationId": "updateOrder",
                        "summary": "Update order",
                        "description": "Update an existing order by ID",
                        "parameters": [
                            {
                                "name": "orderId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                                "description": "The order ID"
                            }
                        ],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string", "enum": ["pending", "completed", "cancelled"]},
                                            "total": {"type": "number"},
                                            "items": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "product_id": {"type": "string"},
                                                        "name": {"type": "string"},
                                                        "quantity": {"type": "integer"},
                                                        "price": {"type": "number"}
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Order updated successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Order"}
                                    }
                                }
                            },
                            "404": {"description": "Order not found"}
                        }
                    },
                    "delete": {
                        "operationId": "deleteOrder",
                        "summary": "Delete order",
                        "description": "Delete an existing order by ID",
                        "parameters": [
                            {
                                "name": "orderId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                                "description": "The order ID"
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "Order deleted successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "message": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            },
                            "404": {"description": "Order not found"}
                        }
                    }
                },
                "/order": {
                    "post": {
                        "operationId": "createOrder",
                        "summary": "Create new order",
                        "description": "Create a new order with customer and item information",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "customer_id": {"type": "string", "description": "Customer identifier"},
                                            "items": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "product_id": {"type": "string"},
                                                        "name": {"type": "string"},
                                                        "quantity": {"type": "integer"},
                                                        "price": {"type": "number"}
                                                    }
                                                }
                                            }
                                        },
                                        "required": ["customer_id", "items"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "description": "Order created successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Order"}
                                    }
                                }
                            }
                        }
                    }
                },
                "/products": {
                    "get": {
                        "operationId": "listProducts",
                        "summary": "List all products",
                        "description": "Retrieve a list of all products in the catalog",
                        "responses": {
                            "200": {
                                "description": "List of products",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "products": {
                                                    "type": "array",
                                                    "items": {"$ref": "#/components/schemas/Product"}
                                                },
                                                "count": {"type": "integer"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/product": {
                    "post": {
                        "operationId": "createProduct",
                        "summary": "Create new product",
                        "description": "Create a new product in the catalog",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string", "description": "Product name"},
                                            "price": {"type": "number", "description": "Product price"},
                                            "category": {"type": "string", "description": "Product category"},
                                            "stock": {"type": "integer", "description": "Stock quantity"}
                                        },
                                        "required": ["name", "price"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "description": "Product created successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Product"}
                                    }
                                }
                            }
                        }
                    }
                },
                "/product/{productId}": {
                    "get": {
                        "operationId": "getProduct",
                        "summary": "Get specific product",
                        "description": "Retrieve details of a specific product by ID",
                        "parameters": [
                            {
                                "name": "productId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                                "description": "The product ID"
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "Product details",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Product"}
                                    }
                                }
                            },
                            "404": {"description": "Product not found"}
                        }
                    },
                    "put": {
                        "operationId": "updateProduct",
                        "summary": "Update product",
                        "description": "Update an existing product by ID",
                        "parameters": [
                            {
                                "name": "productId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                                "description": "The product ID"
                            }
                        ],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "price": {"type": "number"},
                                            "category": {"type": "string"},
                                            "stock": {"type": "integer"}
                                        }
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Product updated successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Product"}
                                    }
                                }
                            },
                            "404": {"description": "Product not found"}
                        }
                    },
                    "delete": {
                        "operationId": "deleteProduct",
                        "summary": "Delete product",
                        "description": "Delete an existing product by ID",
                        "parameters": [
                            {
                                "name": "productId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                                "description": "The product ID"
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "Product deleted successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "message": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            },
                            "404": {"description": "Product not found"}
                        }
                    }
                },
                "/customers": {
                    "get": {
                        "operationId": "listCustomers",
                        "summary": "List all customers",
                        "description": "Retrieve a list of all customers",
                        "responses": {
                            "200": {
                                "description": "List of customers",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "customers": {
                                                    "type": "array",
                                                    "items": {"$ref": "#/components/schemas/Customer"}
                                                },
                                                "count": {"type": "integer"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/customer": {
                    "post": {
                        "operationId": "createCustomer",
                        "summary": "Create new customer",
                        "description": "Create a new customer record",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string", "description": "Customer name"},
                                            "email": {"type": "string", "format": "email", "description": "Customer email"},
                                            "phone": {"type": "string", "description": "Customer phone number"}
                                        },
                                        "required": ["name", "email"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "description": "Customer created successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Customer"}
                                    }
                                }
                            }
                        }
                    }
                },
                "/customer/{customerId}": {
                    "get": {
                        "operationId": "getCustomer",
                        "summary": "Get specific customer",
                        "description": "Retrieve details of a specific customer by ID",
                        "parameters": [
                            {
                                "name": "customerId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                                "description": "The customer ID"
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "Customer details",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Customer"}
                                    }
                                }
                            },
                            "404": {"description": "Customer not found"}
                        }
                    },
                    "put": {
                        "operationId": "updateCustomer",
                        "summary": "Update customer",
                        "description": "Update an existing customer by ID",
                        "parameters": [
                            {
                                "name": "customerId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                                "description": "The customer ID"
                            }
                        ],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "email": {"type": "string", "format": "email"},
                                            "phone": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Customer updated successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Customer"}
                                    }
                                }
                            },
                            "404": {"description": "Customer not found"}
                        }
                    },
                    "delete": {
                        "operationId": "deleteCustomer",
                        "summary": "Delete customer",
                        "description": "Delete an existing customer by ID",
                        "parameters": [
                            {
                                "name": "customerId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                                "description": "The customer ID"
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "Customer deleted successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "message": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            },
                            "404": {"description": "Customer not found"}
                        }
                    }
                },
                "/inventory": {
                    "get": {
                        "operationId": "getInventory",
                        "summary": "Check inventory levels",
                        "description": "Retrieve current inventory levels for all products",
                        "responses": {
                            "200": {
                                "description": "Inventory information",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "inventory": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "object",
                                                        "properties": {
                                                            "product_id": {"type": "string"},
                                                            "name": {"type": "string"},
                                                            "stock": {"type": "integer"}
                                                        }
                                                    }
                                                },
                                                "total_products": {"type": "integer"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/analytics/sales": {
                    "get": {
                        "operationId": "getSalesAnalytics",
                        "summary": "Get sales analytics",
                        "description": "Retrieve sales analytics and metrics",
                        "responses": {
                            "200": {
                                "description": "Sales analytics data",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "total_sales": {"type": "number", "description": "Total sales amount"},
                                                "completed_orders": {"type": "integer", "description": "Number of completed orders"},
                                                "average_order_value": {"type": "number", "description": "Average order value"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/purchase": {
                    "post": {
                        "operationId": "createPurchase",
                        "summary": "Process purchase",
                        "description": "Process a purchase transaction for an order",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "order_id": {"type": "string", "description": "Order identifier"},
                                            "amount": {"type": "number", "description": "Purchase amount"},
                                            "payment_method": {"type": "string", "description": "Payment method (e.g., credit_card)"}
                                        },
                                        "required": ["order_id", "amount"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "description": "Purchase processed successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Purchase"}
                                    }
                                }
                            }
                        }
                    }
                },
                "/purchases": {
                    "get": {
                        "operationId": "listPurchases",
                        "summary": "List all purchases",
                        "description": "Retrieve a list of all purchase transactions",
                        "responses": {
                            "200": {
                                "description": "List of purchases",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "purchases": {
                                                    "type": "array",
                                                    "items": {"$ref": "#/components/schemas/Purchase"}
                                                },
                                                "count": {"type": "integer"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "Order": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Order identifier"},
                            "customer_id": {"type": "string", "description": "Customer identifier"},
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "product_id": {"type": "string"},
                                        "name": {"type": "string"},
                                        "quantity": {"type": "integer"},
                                        "price": {"type": "number"}
                                    }
                                }
                            },
                            "total": {"type": "number", "description": "Total order amount"},
                            "status": {"type": "string", "enum": ["pending", "completed", "cancelled"]},
                            "created_at": {"type": "string", "format": "date-time"}
                        }
                    },
                    "Product": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Product identifier"},
                            "name": {"type": "string", "description": "Product name"},
                            "price": {"type": "number", "description": "Product price"},
                            "category": {"type": "string", "description": "Product category"},
                            "stock": {"type": "integer", "description": "Available stock quantity"}
                        }
                    },
                    "Customer": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Customer identifier"},
                            "name": {"type": "string", "description": "Customer name"},
                            "email": {"type": "string", "format": "email", "description": "Customer email"},
                            "phone": {"type": "string", "description": "Customer phone number"}
                        }
                    },
                    "Purchase": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Purchase identifier"},
                            "order_id": {"type": "string", "description": "Associated order ID"},
                            "payment_method": {"type": "string", "description": "Payment method used"},
                            "payment_status": {"type": "string", "enum": ["pending", "completed", "failed"]},
                            "amount": {"type": "number", "description": "Purchase amount"},
                            "transaction_id": {"type": "string", "description": "Transaction identifier"},
                            "processed_at": {"type": "string", "format": "date-time"}
                        }
                    }
                }
            }
        }

    def create_cognito_user_pool(self, gateway_name):
        """Create Cognito User Pool for OAuth authentication"""
        print(f"Creating Cognito User Pool for {gateway_name}...")
        
        user_pool_name = f"{gateway_name}-user-pool-{self.unique_suffix}"
        
        try:
            # Create user pool
            user_pool_response = self.cognito_client.create_user_pool(
                PoolName=user_pool_name,
                Policies={
                    'PasswordPolicy': {
                        'MinimumLength': 8,
                        'RequireUppercase': True,
                        'RequireLowercase': True,
                        'RequireNumbers': True,
                        'RequireSymbols': True,
                        'TemporaryPasswordValidityDays': 7
                    }
                },
                DeletionProtection='INACTIVE'
            )
            
            user_pool_id = user_pool_response['UserPool']['Id']
            print(f"✅ Created User Pool: {user_pool_id}")
            
            # Create domain
            domain_name = f"{gateway_name}-domain-{self.unique_suffix}"
            try:
                self.cognito_client.create_user_pool_domain(
                    Domain=domain_name,
                    UserPoolId=user_pool_id
                )
                print(f"✅ Created Domain: {domain_name}")
            except Exception as e:
                print(f"⚠️  Domain creation failed (may already exist): {e}")
            
            # Create resource server first
            resource_server_name = f"{gateway_name}-resource-server"
            scope_name = f"{gateway_name}/genesis-gateway:invoke"
            
            try:
                self.cognito_client.create_resource_server(
                    UserPoolId=user_pool_id,
                    Identifier=gateway_name,
                    Name=resource_server_name,
                    Scopes=[
                        {
                            'ScopeName': 'genesis-gateway:invoke',
                            'ScopeDescription': 'Invoke gateway tools'
                        }
                    ]
                )
                print(f"✅ Created Resource Server: {resource_server_name}")
            except Exception as e:
                print(f"⚠️  Resource server creation failed: {e}")
            
            # Create app client
            client_name = f"{gateway_name}-client-{self.unique_suffix}"
            client_response = self.cognito_client.create_user_pool_client(
                UserPoolId=user_pool_id,
                ClientName=client_name,
                GenerateSecret=True,
                AllowedOAuthFlows=['client_credentials'],
                AllowedOAuthScopes=[scope_name],
                AllowedOAuthFlowsUserPoolClient=True,
                SupportedIdentityProviders=['COGNITO']
            )
            
            client_id = client_response['UserPoolClient']['ClientId']
            client_secret = client_response['UserPoolClient']['ClientSecret']
            
            print(f"✅ Created App Client: {client_id}")
            
            return {
                'user_pool_id': user_pool_id,
                'user_pool_name': user_pool_name,
                'domain_name': domain_name,
                'client_id': client_id,
                'client_secret': client_secret,
                'discovery_url': f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration",
                'token_endpoint': f"https://{domain_name}.auth.{self.region}.amazoncognito.com/oauth2/token"
            }
            
        except Exception as e:
            print(f"❌ Failed to create Cognito resources: {e}")
            raise

    def get_or_create_service_role(self):
        """Get or create IAM service role for AgentCore Gateway"""
        role_name = f"AmazonBedrockAgentCoreGatewayServiceRole-{self.unique_suffix}"
        
        try:
            # Try to get existing role
            response = self.iam_client.get_role(RoleName=role_name)
            print(f"✅ Using existing IAM role: {role_name}")
            return response['Role']['Arn']
        except self.iam_client.exceptions.NoSuchEntityException:
            # Create new role
            print(f"Creating IAM service role: {role_name}")
            
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "bedrock-agentcore.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
            
            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description=f"Service role for AgentCore Gateway {role_name}"
            )
            
            # Create comprehensive policy for AgentCore Gateway with all required permissions
            # Based on the permissions we discovered during troubleshooting
            account_id = boto3.client('sts').get_caller_identity()['Account']
            
            policy_document = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "CloudWatchLogs",
                        "Effect": "Allow",
                        "Action": [
                            "logs:CreateLogGroup",
                            "logs:CreateLogStream",
                            "logs:PutLogEvents"
                        ],
                        "Resource": f"arn:aws:logs:{self.region}:{account_id}:*"
                    },
                    {
                        "Sid": "WorkloadIdentityTokenAccess",
                        "Effect": "Allow",
                        "Action": "bedrock-agentcore:GetWorkloadAccessToken",
                        "Resource": [
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:workload-identity-directory/default",
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:workload-identity-directory/default/workload-identity/*"
                        ]
                    },
                    {
                        "Sid": "ResourceApiKeyAccess",
                        "Effect": "Allow",
                        "Action": "bedrock-agentcore:GetResourceApiKey",
                        "Resource": [
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:token-vault/default",
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:token-vault/default/apikeycredentialprovider/*",
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:workload-identity-directory/default",
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:workload-identity-directory/default/workload-identity/*"
                        ]
                    },
                    {
                        "Sid": "SecretsManagerAccess",
                        "Effect": "Allow",
                        "Action": "secretsmanager:GetSecretValue",
                        "Resource": f"arn:aws:secretsmanager:{self.region}:{account_id}:secret:*"
                    },
                    {
                        "Sid": "AgentCoreGatewayOperations",
                        "Effect": "Allow",
                        "Action": [
                            "bedrock-agentcore:InvokeGateway",
                            "bedrock-agentcore:GetGateway",
                            "bedrock-agentcore:ListGatewayTargets",
                            "bedrock-agentcore:GetGatewayTarget"
                        ],
                        "Resource": [
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:gateway/*",
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:gateway-target/*"
                        ]
                    }
                ]
            }
            
            policy_name = f"AgentCoreGatewayPolicy-{self.unique_suffix}"
            try:
                policy_response = self.iam_client.create_policy(
                    PolicyName=policy_name,
                    PolicyDocument=json.dumps(policy_document),
                    Description="Basic policy for AgentCore Gateway"
                )
                policy_arn = policy_response['Policy']['Arn']
            except self.iam_client.exceptions.EntityAlreadyExistsException:
                # Policy already exists, get its ARN
                account_id = boto3.client('sts').get_caller_identity()['Account']
                policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"
            
            # Attach the policy
            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn=policy_arn
            )
            
            print(f"✅ Created IAM role: {role_name}")
            return response['Role']['Arn']

    def fix_existing_gateway_permissions(self, gateway_role_name):
        """Fix permissions for an existing gateway role"""
        print(f"🔧 Fixing permissions for existing gateway role: {gateway_role_name}")
        
        try:
            # Get account ID
            account_id = boto3.client('sts').get_caller_identity()['Account']
            
            # Comprehensive policy for gateway operations
            policy_document = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "WorkloadIdentityTokenAccess",
                        "Effect": "Allow",
                        "Action": "bedrock-agentcore:GetWorkloadAccessToken",
                        "Resource": [
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:workload-identity-directory/default",
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:workload-identity-directory/default/workload-identity/*"
                        ]
                    },
                    {
                        "Sid": "ResourceApiKeyAccess",
                        "Effect": "Allow",
                        "Action": "bedrock-agentcore:GetResourceApiKey",
                        "Resource": [
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:token-vault/default",
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:token-vault/default/apikeycredentialprovider/*",
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:workload-identity-directory/default",
                            f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:workload-identity-directory/default/workload-identity/*"
                        ]
                    },
                    {
                        "Sid": "SecretsManagerAccess",
                        "Effect": "Allow",
                        "Action": "secretsmanager:GetSecretValue",
                        "Resource": f"arn:aws:secretsmanager:{self.region}:{account_id}:secret:*"
                    }
                ]
            }
            
            # Add the policy as an inline policy
            policy_name = "WorkloadIdentityTokenAccess"
            self.iam_client.put_role_policy(
                RoleName=gateway_role_name,
                PolicyName=policy_name,
                PolicyDocument=json.dumps(policy_document)
            )
            
            print(f"✅ Added comprehensive permissions to role: {gateway_role_name}")
            print(f"   Policy name: {policy_name}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to fix gateway permissions: {e}")
            return False

    def fix_gateway_target_domain(self, gateway_id, target_id, correct_domain):
        """Fix the domain in an existing gateway target"""
        print(f"🔧 Fixing domain for gateway target...")
        print(f"   Gateway ID: {gateway_id}")
        print(f"   Target ID: {target_id}")
        print(f"   Correct domain: {correct_domain}")
        
        try:
            # Get current target configuration
            response = self.agentcore_client.get_gateway_target(
                gatewayIdentifier=gateway_id,
                targetId=target_id
            )
            
            # Extract and parse the OpenAPI spec
            current_config = response['targetConfiguration']
            openapi_payload = current_config['mcp']['openApiSchema']['inlinePayload']
            openapi_spec = json.loads(openapi_payload)
            
            # Update the server URL
            old_domain = openapi_spec['servers'][0]['url']
            openapi_spec['servers'][0]['url'] = correct_domain
            
            print(f"   Changed domain: {old_domain} → {correct_domain}")
            
            # Update the target configuration
            updated_config = {
                "mcp": {
                    "openApiSchema": {
                        "inlinePayload": json.dumps(openapi_spec)
                    }
                }
            }
            
            # Get existing credential provider configurations
            credential_configs = response.get('credentialProviderConfigurations', [])
            
            # Update the target
            self.agentcore_client.update_gateway_target(
                gatewayIdentifier=gateway_id,
                targetId=target_id,
                name=response['name'],
                description=response['description'],
                targetConfiguration=updated_config,
                credentialProviderConfigurations=credential_configs
            )
            
            print(f"✅ Successfully updated gateway target domain")
            return True
            
        except Exception as e:
            print(f"❌ Failed to fix gateway target domain: {e}")
            return False

    def update_gateway_target_with_new_spec(self, gateway_id, target_id, api_base_url=None):
        """Update gateway target with new OpenAPI specification including PUT and DELETE operations"""
        print(f"🔄 Updating gateway target with new OpenAPI specification...")
        print(f"   Gateway ID: {gateway_id}")
        print(f"   Target ID: {target_id}")
        
        try:
            # Get current target configuration
            print("🔍 Retrieving current target configuration...")
            response = self.agentcore_client.get_gateway_target(
                gatewayIdentifier=gateway_id,
                targetId=target_id
            )
            
            current_name = response['name']
            current_description = response['description']
            credential_configs = response.get('credentialProviderConfigurations', [])
            
            # Get current API base URL if not provided
            if api_base_url is None:
                current_config = response['targetConfiguration']
                openapi_payload = current_config['mcp']['openApiSchema']['inlinePayload']
                current_spec = json.loads(openapi_payload)
                api_base_url = current_spec['servers'][0]['url']
            
            print(f"   Current name: {current_name}")
            print(f"   API base URL: {api_base_url}")
            print()
            
            # Generate new OpenAPI spec with PUT and DELETE operations
            print("📖 Generating updated OpenAPI specification...")
            openapi_spec = self.generate_openapi_spec(api_base_url)
            
            # Count operations
            total_operations = sum(len(methods) for methods in openapi_spec['paths'].values())
            print(f"   Total endpoints: {len(openapi_spec['paths'])}")
            print(f"   Total operations: {total_operations}")
            print()
            
            # Prepare updated target configuration
            print("🔧 Preparing updated configuration...")
            updated_config = {
                "mcp": {
                    "openApiSchema": {
                        "inlinePayload": json.dumps(openapi_spec)
                    }
                }
            }
            
            # Update the gateway target
            print("⬆️  Updating gateway target...")
            self.agentcore_client.update_gateway_target(
                gatewayIdentifier=gateway_id,
                targetId=target_id,
                name=current_name,
                description=current_description,
                targetConfiguration=updated_config,
                credentialProviderConfigurations=credential_configs
            )
            
            print()
            print("=" * 60)
            print("✅ Gateway target updated successfully!")
            print()
            print(f"Gateway ID: {gateway_id}")
            print(f"Target ID: {target_id}")
            print(f"Total operations: {total_operations}")
            print()
            print("New operations added:")
            print("  - PUT /order/{orderId} (updateOrder)")
            print("  - DELETE /order/{orderId} (deleteOrder)")
            print("  - PUT /product/{productId} (updateProduct)")
            print("  - DELETE /product/{productId} (deleteProduct)")
            print("  - PUT /customer/{customerId} (updateCustomer)")
            print("  - DELETE /customer/{customerId} (deleteCustomer)")
            print()
            print("Next steps:")
            print("1. Test the new operations using test_gateway_connection.py")
            print("2. Verify new tools appear in QuickSuite")
            print("3. Try natural language commands like:")
            print("   - 'Update order ord_001 status to completed'")
            print("   - 'Delete product prod_004'")
            print("=" * 60)
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to update gateway target: {e}")
            import traceback
            traceback.print_exc()
            return False

    def create_gateway(self, gateway_name, cognito_config, role_arn):
        """Create the AgentCore Gateway using boto3"""
        print(f"Creating AgentCore Gateway: {gateway_name}")
        
        try:
            response = self.agentcore_client.create_gateway(
                name=gateway_name,
                description=f"Retail Demo API Gateway - {self.timestamp}",
                roleArn=role_arn,
                protocolType='MCP',
                authorizerType='CUSTOM_JWT',
                authorizerConfiguration={
                    'customJWTAuthorizer': {
                        'discoveryUrl': cognito_config['discovery_url'],
                        'allowedClients': [cognito_config['client_id']]
                    }
                },
                exceptionLevel='DEBUG'
            )
            
            gateway_id = response['gatewayId']
            gateway_url = response['gatewayUrl']
            
            print(f"✅ Created Gateway: {gateway_id}")
            print(f"   URL: {gateway_url}")
            
            return {
                'gateway_id': gateway_id,
                'gateway_url': gateway_url,
                'gateway_arn': response['gatewayArn']
            }
            
        except Exception as e:
            print(f"❌ Failed to create gateway: {e}")
            raise

    def create_api_key_credential_provider(self):
        """Create API key credential provider for public API (empty key)"""
        print("Creating API key credential provider...")
        
        try:
            response = self.agentcore_client.create_api_key_credential_provider(
                name=f"retail-api-key-{self.unique_suffix}",
                apiKey="public-api-no-key-required"  # Placeholder for public API
            )
            
            provider_arn = response['credentialProviderArn']
            print(f"✅ Created API Key Credential Provider: {provider_arn}")
            return provider_arn
            
        except Exception as e:
            print(f"❌ Failed to create API key credential provider: {e}")
            raise

    def create_openapi_target(self, gateway_id, openapi_spec):
        """Create OpenAPI target for the gateway using boto3"""
        print("Creating OpenAPI target...")
        
        try:
            # Create API key credential provider first
            provider_arn = self.create_api_key_credential_provider()
            
            # Target configuration for OpenAPI schema
            target_config = {
                "mcp": {
                    "openApiSchema": {
                        "inlinePayload": json.dumps(openapi_spec)
                    }
                }
            }
            
            # Credential provider configuration using API_KEY
            credential_config = [
                {
                    "credentialProviderType": "API_KEY",
                    "credentialProvider": {
                        "apiKeyCredentialProvider": {
                            "providerArn": provider_arn,
                            "credentialLocation": "HEADER"
                        }
                    }
                }
            ]
            
            response = self.agentcore_client.create_gateway_target(
                gatewayIdentifier=gateway_id,
                name=f"retail-api-target-{self.unique_suffix}",
                description="Retail Demo API OpenAPI Target",
                targetConfiguration=target_config,
                credentialProviderConfigurations=credential_config
            )
            
            target_id = response['targetId']
            print(f"✅ Created Target: {target_id}")
            
            return target_id
            
        except Exception as e:
            print(f"❌ Failed to create target: {e}")
            raise

    def wait_for_gateway_ready(self, gateway_id, max_wait_time=300):
        """Wait for gateway to be ready"""
        print("Waiting for gateway to be ready...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait_time:
            try:
                response = self.agentcore_client.get_gateway(gatewayIdentifier=gateway_id)
                status = response['status']
                
                if status == 'READY':
                    print("✅ Gateway is ready!")
                    return True
                elif status == 'FAILED':
                    print("❌ Gateway creation failed!")
                    return False
                else:
                    print(f"   Status: {status} - waiting...")
                    time.sleep(10)  # nosemgrep: arbitrary-sleep - Required for AWS gateway provisioning
                    
            except Exception as e:
                print(f"   Error checking status: {e}")
                time.sleep(10)  # nosemgrep: arbitrary-sleep - Required for AWS gateway provisioning
        
        print("❌ Timeout waiting for gateway to be ready")
        return False

    def save_configuration(self, gateway_config, cognito_config, target_id, gateway_name):
        """Save the deployment configuration"""
        config = {
            "gateway_url": gateway_config['gateway_url'],
            "gateway_id": gateway_config['gateway_id'],
            "client_id": cognito_config['client_id'],
            "client_secret": cognito_config['client_secret'],
            "token_endpoint": cognito_config['token_endpoint'],
            "scope": f"{gateway_name}/genesis-gateway:invoke",
            "region": self.region,
            "target_id": target_id,
            "deployment_info": {
                "deployed_at": self.timestamp,
                "user_pool_id": cognito_config['user_pool_id'],
                "domain_name": cognito_config['domain_name'],
                "method": "boto3"
            }
        }
        
        config_filename = f"retail_gateway_config_boto3_{self.unique_suffix}.json"
        with open(config_filename, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Configuration saved to: {config_filename}")
        return config_filename

    def deploy(self, gateway_name=None, api_base_url="https://api.yourcompany.com"):
        """Deploy the complete gateway setup using boto3"""
        if gateway_name is None:
            gateway_name = f"retail-demo-boto3-{self.unique_suffix}"
        
        print(f"🚀 Starting boto3-based deployment of {gateway_name}")
        print(f"   Timestamp: {self.timestamp}")
        print(f"   Region: {self.region}")
        print("=" * 60)
        
        try:
            # Step 1: Create Cognito resources
            cognito_config = self.create_cognito_user_pool(gateway_name)
            
            # Step 2: Create/get IAM role
            role_arn = self.get_or_create_service_role()
            
            # Wait for IAM propagation
            print("⏳ Waiting for IAM propagation...")
            time.sleep(30)  # nosemgrep: arbitrary-sleep - Required for IAM role propagation across AWS
            
            # Step 3: Create gateway
            gateway_config = self.create_gateway(gateway_name, cognito_config, role_arn)
            
            # Step 4: Wait for gateway to be ready
            if not self.wait_for_gateway_ready(gateway_config['gateway_id']):
                raise Exception("Gateway failed to become ready")
            
            # Step 5: Create OpenAPI target
            openapi_spec = self.generate_openapi_spec(api_base_url)
            target_id = self.create_openapi_target(gateway_config['gateway_id'], openapi_spec)
            
            # Step 6: Save configuration
            config_file = self.save_configuration(gateway_config, cognito_config, target_id, gateway_name)
            
            print("\n" + "=" * 60)
            print("🎉 Boto3-based deployment completed successfully!")
            print(f"Gateway Name: {gateway_name}")
            print(f"Gateway URL: {gateway_config['gateway_url']}")
            print(f"Configuration: {config_file}")
            print("\nNext steps:")
            print("1. Test the gateway using the generated config file")
            print("2. Integrate with QuickSuite using Machine-to-Machine OAuth")
            print("3. Use the gateway tools in your agents")
            
            return {
                'gateway_config': gateway_config,
                'cognito_config': cognito_config,
                'target_id': target_id,
                'config_file': config_file
            }
            
        except Exception as e:
            print(f"\n❌ Deployment failed: {e}")
            print("You may need to clean up partially created resources.")
            raise

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Deploy AgentCore Gateway using boto3')
    parser.add_argument('--name', help='Gateway name (default: auto-generated)')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--api-url', default='https://api.yourcompany.com', 
                       help='Retail API base URL (default: https://api.yourcompany.com)')
    
    # Fix existing gateway options
    parser.add_argument('--fix-permissions', help='Fix IAM permissions for existing gateway role')
    parser.add_argument('--fix-domain', nargs=3, metavar=('GATEWAY_ID', 'TARGET_ID', 'DOMAIN'),
                       help='Fix domain for existing gateway target: GATEWAY_ID TARGET_ID DOMAIN')
    
    # Update gateway target with new operations
    parser.add_argument('--update-target', nargs=2, metavar=('GATEWAY_ID', 'TARGET_ID'),
                       help='Update gateway target with new PUT and DELETE operations: GATEWAY_ID TARGET_ID')
    
    args = parser.parse_args()
    
    deployer = RetailGatewayDeployerBoto3(region=args.region)
    
    # Handle fix operations
    if args.fix_permissions:
        print("🔧 Fixing IAM permissions for existing gateway...")
        success = deployer.fix_existing_gateway_permissions(args.fix_permissions)
        if success:
            print("✅ IAM permissions fixed successfully!")
        else:
            print("❌ Failed to fix IAM permissions")
        return
    
    if args.fix_domain:
        gateway_id, target_id, domain = args.fix_domain
        print("🔧 Fixing domain for existing gateway target...")
        success = deployer.fix_gateway_target_domain(gateway_id, target_id, domain)
        if success:
            print("✅ Domain fixed successfully!")
        else:
            print("❌ Failed to fix domain")
        return
    
    if args.update_target:
        gateway_id, target_id = args.update_target
        print("🔄 Updating gateway target with new operations...")
        success = deployer.update_gateway_target_with_new_spec(gateway_id, target_id, args.api_url)
        if success:
            print("✅ Gateway target updated successfully!")
        else:
            print("❌ Failed to update gateway target")
        return
    
    # Normal deployment
    deployer.deploy(gateway_name=args.name, api_base_url=args.api_url)

if __name__ == "__main__":
    main()