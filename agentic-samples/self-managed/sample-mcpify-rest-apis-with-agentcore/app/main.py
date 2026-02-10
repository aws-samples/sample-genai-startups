from flask import Flask, jsonify, request
from datetime import datetime
import uuid
import json
from functools import wraps
import boto3
from botocore.exceptions import ClientError
from decimal import Decimal
import os

app = Flask(__name__)

# Custom JSON encoder to handle Decimal types
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

app.json_encoder = DecimalEncoder

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
table = dynamodb.Table('RetailData')

app.logger.info("DynamoDB client initialized for table: RetailData")

# Optional API key validation (for AgentCore Gateway compatibility)
def validate_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for API key in headers (optional)
        api_key = request.headers.get('X-API-Key') or request.headers.get('X-Dummy-Auth')
        
        # For now, we accept any API key or no API key (public access)
        # In production, you might want to validate against a list of valid keys
        
        # Log the API key usage for debugging
        if api_key:
            app.logger.info(f"Request with API key: {api_key[:10]}...")
        else:
            app.logger.info("Request without API key (public access)")
            
        return f(*args, **kwargs)
    return decorated_function

# DynamoDB Data Access Functions

def convert_floats_to_decimal(obj):
    """Recursively convert all float values to Decimal for DynamoDB"""
    if isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, float):
        return Decimal(str(obj))
    return obj

def create_order(order_data):
    """Create a new order in DynamoDB"""
    try:
        item = {
            'PK': f"ORDER#{order_data['id']}",
            'SK': 'METADATA',
            'GSI1PK': 'ORDER',
            'GSI1SK': order_data['created_at'],
            **order_data
        }
        table.put_item(Item=item)
        return order_data
    except ClientError as e:
        app.logger.error(f"Error creating order: {e}")
        raise

def get_order(order_id):
    """Get an order by ID from DynamoDB"""
    try:
        response = table.get_item(
            Key={'PK': f"ORDER#{order_id}", 'SK': 'METADATA'}
        )
        if 'Item' in response:
            item = response['Item']
            # Remove DynamoDB keys from response
            item.pop('PK', None)
            item.pop('SK', None)
            item.pop('GSI1PK', None)
            item.pop('GSI1SK', None)
            return item
        return None
    except ClientError as e:
        app.logger.error(f"Error getting order: {e}")
        raise

def list_orders():
    """List all orders from DynamoDB"""
    try:
        response = table.query(
            IndexName='GSI1',
            KeyConditionExpression='GSI1PK = :pk',
            ExpressionAttributeValues={':pk': 'ORDER'}
        )
        items = response.get('Items', [])
        # Clean up DynamoDB keys
        for item in items:
            item.pop('PK', None)
            item.pop('SK', None)
            item.pop('GSI1PK', None)
            item.pop('GSI1SK', None)
        return items
    except ClientError as e:
        app.logger.error(f"Error listing orders: {e}")
        raise

def update_order(order_id, updates):
    """Update an order in DynamoDB"""
    try:
        # Build update expression
        update_expr = "SET "
        expr_attr_values = {}
        expr_attr_names = {}
        
        for key, value in updates.items():
            if key not in ['id', 'PK', 'SK', 'GSI1PK', 'GSI1SK']:
                attr_name = f"#{key}"
                attr_value = f":{key}"
                update_expr += f"{attr_name} = {attr_value}, "
                expr_attr_names[attr_name] = key
                expr_attr_values[attr_value] = value
        
        update_expr = update_expr.rstrip(', ')
        
        response = table.update_item(
            Key={'PK': f"ORDER#{order_id}", 'SK': 'METADATA'},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values,
            ReturnValues='ALL_NEW'
        )
        
        item = response['Attributes']
        item.pop('PK', None)
        item.pop('SK', None)
        item.pop('GSI1PK', None)
        item.pop('GSI1SK', None)
        return item
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return None
        app.logger.error(f"Error updating order: {e}")
        raise

def delete_order(order_id):
    """Delete an order from DynamoDB"""
    try:
        table.delete_item(
            Key={'PK': f"ORDER#{order_id}", 'SK': 'METADATA'}
        )
        return True
    except ClientError as e:
        app.logger.error(f"Error deleting order: {e}")
        raise

def create_product(product_data):
    """Create a new product in DynamoDB"""
    try:
        item = {
            'PK': f"PRODUCT#{product_data['id']}",
            'SK': 'METADATA',
            'GSI1PK': 'PRODUCT',
            'GSI1SK': product_data['name'],
            **product_data
        }
        table.put_item(Item=item)
        return product_data
    except ClientError as e:
        app.logger.error(f"Error creating product: {e}")
        raise

def get_product(product_id):
    """Get a product by ID from DynamoDB"""
    try:
        response = table.get_item(
            Key={'PK': f"PRODUCT#{product_id}", 'SK': 'METADATA'}
        )
        if 'Item' in response:
            item = response['Item']
            item.pop('PK', None)
            item.pop('SK', None)
            item.pop('GSI1PK', None)
            item.pop('GSI1SK', None)
            return item
        return None
    except ClientError as e:
        app.logger.error(f"Error getting product: {e}")
        raise

def list_products():
    """List all products from DynamoDB"""
    try:
        response = table.query(
            IndexName='GSI1',
            KeyConditionExpression='GSI1PK = :pk',
            ExpressionAttributeValues={':pk': 'PRODUCT'}
        )
        items = response.get('Items', [])
        for item in items:
            item.pop('PK', None)
            item.pop('SK', None)
            item.pop('GSI1PK', None)
            item.pop('GSI1SK', None)
        return items
    except ClientError as e:
        app.logger.error(f"Error listing products: {e}")
        raise

def update_product(product_id, updates):
    """Update a product in DynamoDB"""
    try:
        update_expr = "SET "
        expr_attr_values = {}
        expr_attr_names = {}
        
        for key, value in updates.items():
            if key not in ['id', 'PK', 'SK', 'GSI1PK', 'GSI1SK']:
                attr_name = f"#{key}"
                attr_value = f":{key}"
                update_expr += f"{attr_name} = {attr_value}, "
                expr_attr_names[attr_name] = key
                expr_attr_values[attr_value] = value
        
        update_expr = update_expr.rstrip(', ')
        
        response = table.update_item(
            Key={'PK': f"PRODUCT#{product_id}", 'SK': 'METADATA'},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values,
            ReturnValues='ALL_NEW'
        )
        
        item = response['Attributes']
        item.pop('PK', None)
        item.pop('SK', None)
        item.pop('GSI1PK', None)
        item.pop('GSI1SK', None)
        return item
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return None
        app.logger.error(f"Error updating product: {e}")
        raise

def delete_product(product_id):
    """Delete a product from DynamoDB"""
    try:
        table.delete_item(
            Key={'PK': f"PRODUCT#{product_id}", 'SK': 'METADATA'}
        )
        return True
    except ClientError as e:
        app.logger.error(f"Error deleting product: {e}")
        raise

def create_customer(customer_data):
    """Create a new customer in DynamoDB"""
    try:
        item = {
            'PK': f"CUSTOMER#{customer_data['id']}",
            'SK': 'METADATA',
            'GSI1PK': 'CUSTOMER',
            'GSI1SK': customer_data['name'],
            **customer_data
        }
        table.put_item(Item=item)
        return customer_data
    except ClientError as e:
        app.logger.error(f"Error creating customer: {e}")
        raise

def get_customer(customer_id):
    """Get a customer by ID from DynamoDB"""
    try:
        response = table.get_item(
            Key={'PK': f"CUSTOMER#{customer_id}", 'SK': 'METADATA'}
        )
        if 'Item' in response:
            item = response['Item']
            item.pop('PK', None)
            item.pop('SK', None)
            item.pop('GSI1PK', None)
            item.pop('GSI1SK', None)
            return item
        return None
    except ClientError as e:
        app.logger.error(f"Error getting customer: {e}")
        raise

def list_customers():
    """List all customers from DynamoDB"""
    try:
        response = table.query(
            IndexName='GSI1',
            KeyConditionExpression='GSI1PK = :pk',
            ExpressionAttributeValues={':pk': 'CUSTOMER'}
        )
        items = response.get('Items', [])
        for item in items:
            item.pop('PK', None)
            item.pop('SK', None)
            item.pop('GSI1PK', None)
            item.pop('GSI1SK', None)
        return items
    except ClientError as e:
        app.logger.error(f"Error listing customers: {e}")
        raise

def update_customer(customer_id, updates):
    """Update a customer in DynamoDB"""
    try:
        update_expr = "SET "
        expr_attr_values = {}
        expr_attr_names = {}
        
        for key, value in updates.items():
            if key not in ['id', 'PK', 'SK', 'GSI1PK', 'GSI1SK']:
                attr_name = f"#{key}"
                attr_value = f":{key}"
                update_expr += f"{attr_name} = {attr_value}, "
                expr_attr_names[attr_name] = key
                expr_attr_values[attr_value] = value
        
        update_expr = update_expr.rstrip(', ')
        
        response = table.update_item(
            Key={'PK': f"CUSTOMER#{customer_id}", 'SK': 'METADATA'},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values,
            ReturnValues='ALL_NEW'
        )
        
        item = response['Attributes']
        item.pop('PK', None)
        item.pop('SK', None)
        item.pop('GSI1PK', None)
        item.pop('GSI1SK', None)
        return item
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return None
        app.logger.error(f"Error updating customer: {e}")
        raise

def delete_customer(customer_id):
    """Delete a customer from DynamoDB"""
    try:
        table.delete_item(
            Key={'PK': f"CUSTOMER#{customer_id}", 'SK': 'METADATA'}
        )
        return True
    except ClientError as e:
        app.logger.error(f"Error deleting customer: {e}")
        raise

def create_purchase(purchase_data):
    """Create a new purchase in DynamoDB"""
    try:
        item = {
            'PK': f"PURCHASE#{purchase_data['id']}",
            'SK': 'METADATA',
            'GSI1PK': 'PURCHASE',
            'GSI1SK': purchase_data['processed_at'],
            **purchase_data
        }
        table.put_item(Item=item)
        return purchase_data
    except ClientError as e:
        app.logger.error(f"Error creating purchase: {e}")
        raise

def get_purchase(purchase_id):
    """Get a purchase by ID from DynamoDB"""
    try:
        response = table.get_item(
            Key={'PK': f"PURCHASE#{purchase_id}", 'SK': 'METADATA'}
        )
        if 'Item' in response:
            item = response['Item']
            item.pop('PK', None)
            item.pop('SK', None)
            item.pop('GSI1PK', None)
            item.pop('GSI1SK', None)
            return item
        return None
    except ClientError as e:
        app.logger.error(f"Error getting purchase: {e}")
        raise

def list_purchases():
    """List all purchases from DynamoDB"""
    try:
        response = table.query(
            IndexName='GSI1',
            KeyConditionExpression='GSI1PK = :pk',
            ExpressionAttributeValues={':pk': 'PURCHASE'}
        )
        items = response.get('Items', [])
        for item in items:
            item.pop('PK', None)
            item.pop('SK', None)
            item.pop('GSI1PK', None)
            item.pop('GSI1SK', None)
        return items
    except ClientError as e:
        app.logger.error(f"Error listing purchases: {e}")
        raise

def seed_data():
    """Seed the database with sample data if empty"""
    try:
        # Check if table is empty
        response = table.scan(Limit=1)
        if response['Count'] > 0:
            app.logger.info("Table already contains data, skipping seed")
            return
        
        app.logger.info("Seeding database with sample data...")
        
        # Sample data
        orders_sample = [
            {
                "id": "ord_001",
                "customer_id": "cust_001",
                "items": [
                    {"product_id": "prod_001", "name": "Laptop", "quantity": 1, "price": Decimal("999.99")},
                    {"product_id": "prod_002", "name": "Mouse", "quantity": 2, "price": Decimal("29.99")}
                ],
                "total": Decimal("1059.97"),
                "status": "completed",
                "created_at": "2024-01-15T10:30:00Z"
            },
            {
                "id": "ord_002",
                "customer_id": "cust_002",
                "items": [
                    {"product_id": "prod_003", "name": "Keyboard", "quantity": 1, "price": Decimal("79.99")}
                ],
                "total": Decimal("79.99"),
                "status": "pending",
                "created_at": "2024-01-16T14:20:00Z"
            }
        ]
        
        products_sample = [
            {"id": "prod_001", "name": "Laptop", "price": Decimal("999.99"), "category": "Electronics", "stock": 50},
            {"id": "prod_002", "name": "Mouse", "price": Decimal("29.99"), "category": "Electronics", "stock": 100},
            {"id": "prod_003", "name": "Keyboard", "price": Decimal("79.99"), "category": "Electronics", "stock": 75},
            {"id": "prod_004", "name": "Monitor", "price": Decimal("299.99"), "category": "Electronics", "stock": 30}
        ]
        
        customers_sample = [
            {"id": "cust_001", "name": "John Doe", "email": "john@example.com", "phone": "+1-555-0123"},
            {"id": "cust_002", "name": "Jane Smith", "email": "jane@example.com", "phone": "+1-555-0124"}
        ]
        
        purchases_sample = [
            {
                "id": "pur_001",
                "order_id": "ord_001",
                "payment_method": "credit_card",
                "payment_status": "completed",
                "amount": Decimal("1059.97"),
                "transaction_id": "txn_abc123",
                "processed_at": "2024-01-15T10:35:00Z"
            }
        ]
        
        # Insert sample data
        for order in orders_sample:
            create_order(order)
        for product in products_sample:
            create_product(product)
        for customer in customers_sample:
            create_customer(customer)
        for purchase in purchases_sample:
            create_purchase(purchase)
        
        app.logger.info(f"Seeded {len(orders_sample)} orders, {len(products_sample)} products, "
                       f"{len(customers_sample)} customers, {len(purchases_sample)} purchases")
        
    except ClientError as e:
        app.logger.error(f"Error seeding data: {e}")

@app.route('/health', methods=['GET'])
@validate_api_key
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})

@app.route('/orders', methods=['GET'])
@validate_api_key
def get_orders():
    try:
        orders = list_orders()
        return jsonify({"orders": orders, "count": len(orders)})
    except Exception as e:
        app.logger.error(f"Error in get_orders: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/order/<order_id>', methods=['GET'])
@validate_api_key
def get_order_endpoint(order_id):
    try:
        order = get_order(order_id)
        if order:
            return jsonify(order)
        return jsonify({"error": "Order not found"}), 404
    except Exception as e:
        app.logger.error(f"Error in get_order: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/order', methods=['POST'])
@validate_api_key
def create_order_endpoint():
    try:
        data = request.get_json()
        new_order = {
            "id": f"ord_{str(uuid.uuid4())[:8]}",
            "customer_id": data.get("customer_id"),
            "items": data.get("items", []),
            "total": sum(item.get("price", 0) * item.get("quantity", 1) for item in data.get("items", [])),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        # Convert floats to Decimal for DynamoDB
        new_order = convert_floats_to_decimal(new_order)
        created_order = create_order(new_order)
        return jsonify(created_order), 201
    except Exception as e:
        app.logger.error(f"Error in create_order: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/order/<order_id>', methods=['PUT'])
@validate_api_key
def update_order_endpoint(order_id):
    try:
        data = request.get_json()
        updated_order = update_order(order_id, data)
        if updated_order:
            return jsonify(updated_order), 200
        return jsonify({"error": "Order not found"}), 404
    except Exception as e:
        app.logger.error(f"Error in update_order: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/order/<order_id>', methods=['DELETE'])
@validate_api_key
def delete_order_endpoint(order_id):
    try:
        # Check if order exists first
        order = get_order(order_id)
        if not order:
            return jsonify({"error": "Order not found"}), 404
        
        delete_order(order_id)
        return jsonify({"message": f"Order {order_id} deleted successfully"}), 200
    except Exception as e:
        app.logger.error(f"Error in delete_order: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/purchase', methods=['POST'])
@validate_api_key
def create_purchase_endpoint():
    try:
        data = request.get_json()
        new_purchase = {
            "id": f"pur_{str(uuid.uuid4())[:8]}",
            "order_id": data.get("order_id"),
            "payment_method": data.get("payment_method", "credit_card"),
            "payment_status": "completed",
            "amount": data.get("amount"),
            "transaction_id": f"txn_{str(uuid.uuid4())[:8]}",
            "processed_at": datetime.utcnow().isoformat() + "Z"
        }
        # Convert floats to Decimal for DynamoDB
        new_purchase = convert_floats_to_decimal(new_purchase)
        created_purchase = create_purchase(new_purchase)
        return jsonify(created_purchase), 201
    except Exception as e:
        app.logger.error(f"Error in create_purchase: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/purchases', methods=['GET'])
@validate_api_key
def get_purchases():
    try:
        purchases = list_purchases()
        return jsonify({"purchases": purchases, "count": len(purchases)})
    except Exception as e:
        app.logger.error(f"Error in get_purchases: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/products', methods=['GET'])
@validate_api_key
def get_products():
    try:
        products = list_products()
        return jsonify({"products": products, "count": len(products)})
    except Exception as e:
        app.logger.error(f"Error in get_products: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/product', methods=['POST'])
@validate_api_key
def create_product_endpoint():
    try:
        data = request.get_json()
        new_product = {
            "id": f"prod_{str(uuid.uuid4())[:8]}",
            "name": data.get("name"),
            "price": data.get("price"),
            "category": data.get("category", "Electronics"),
            "stock": data.get("stock", 0)
        }
        # Convert floats to Decimal for DynamoDB
        new_product = convert_floats_to_decimal(new_product)
        created_product = create_product(new_product)
        return jsonify(created_product), 201
    except Exception as e:
        app.logger.error(f"Error in create_product: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/product/<product_id>', methods=['GET'])
@validate_api_key
def get_product_endpoint(product_id):
    try:
        product = get_product(product_id)
        if product:
            return jsonify(product)
        return jsonify({"error": "Product not found"}), 404
    except Exception as e:
        app.logger.error(f"Error in get_product: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/product/<product_id>', methods=['PUT'])
@validate_api_key
def update_product_endpoint(product_id):
    try:
        data = request.get_json()
        updated_product = update_product(product_id, data)
        if updated_product:
            return jsonify(updated_product), 200
        return jsonify({"error": "Product not found"}), 404
    except Exception as e:
        app.logger.error(f"Error in update_product: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/product/<product_id>', methods=['DELETE'])
@validate_api_key
def delete_product_endpoint(product_id):
    try:
        product = get_product(product_id)
        if not product:
            return jsonify({"error": "Product not found"}), 404
        
        delete_product(product_id)
        return jsonify({"message": f"Product {product_id} deleted successfully"}), 200
    except Exception as e:
        app.logger.error(f"Error in delete_product: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/customers', methods=['GET'])
@validate_api_key
def get_customers():
    try:
        customers = list_customers()
        return jsonify({"customers": customers, "count": len(customers)})
    except Exception as e:
        app.logger.error(f"Error in get_customers: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/customer', methods=['POST'])
@validate_api_key
def create_customer_endpoint():
    try:
        data = request.get_json()
        new_customer = {
            "id": f"cust_{str(uuid.uuid4())[:8]}",
            "name": data.get("name"),
            "email": data.get("email"),
            "phone": data.get("phone", "")
        }
        created_customer = create_customer(new_customer)
        return jsonify(created_customer), 201
    except Exception as e:
        app.logger.error(f"Error in create_customer: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/customer/<customer_id>', methods=['GET'])
@validate_api_key
def get_customer_endpoint(customer_id):
    try:
        customer = get_customer(customer_id)
        if customer:
            return jsonify(customer)
        return jsonify({"error": "Customer not found"}), 404
    except Exception as e:
        app.logger.error(f"Error in get_customer: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/customer/<customer_id>', methods=['PUT'])
@validate_api_key
def update_customer_endpoint(customer_id):
    try:
        data = request.get_json()
        updated_customer = update_customer(customer_id, data)
        if updated_customer:
            return jsonify(updated_customer), 200
        return jsonify({"error": "Customer not found"}), 404
    except Exception as e:
        app.logger.error(f"Error in update_customer: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/customer/<customer_id>', methods=['DELETE'])
@validate_api_key
def delete_customer_endpoint(customer_id):
    try:
        customer = get_customer(customer_id)
        if not customer:
            return jsonify({"error": "Customer not found"}), 404
        
        delete_customer(customer_id)
        return jsonify({"message": f"Customer {customer_id} deleted successfully"}), 200
    except Exception as e:
        app.logger.error(f"Error in delete_customer: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/inventory', methods=['GET'])
@validate_api_key
def get_inventory():
    try:
        products = list_products()
        inventory = [{"product_id": p["id"], "name": p["name"], "stock": p["stock"]} for p in products]
        return jsonify({"inventory": inventory, "total_products": len(inventory)})
    except Exception as e:
        app.logger.error(f"Error in get_inventory: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/analytics/sales', methods=['GET'])
@validate_api_key
def get_sales_analytics():
    try:
        orders = list_orders()
        total_sales = sum(order["total"] for order in orders if order["status"] == "completed")
        completed_orders = len([o for o in orders if o["status"] == "completed"])
        return jsonify({
            "total_sales": total_sales,
            "completed_orders": completed_orders,
            "average_order_value": total_sales / completed_orders if completed_orders > 0 else 0
        })
    except Exception as e:
        app.logger.error(f"Error in get_sales_analytics: {e}")
        return jsonify({"error": "Internal server error"}), 500

# Seed data on module load (works with Gunicorn)
seed_data()

if __name__ == '__main__':
    import os
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)  # nosec B104 - Required for container networking