import boto3
import json
from decimal import Decimal

# Initialize DynamoDB resource
dynamodb = boto3.resource('dynamodb', region_name='eu-central-1')

def load_inventory():
    table = dynamodb.Table('sc-inventory')
    items = [
        {"product_id": "P-001", "name": "Lithium-Ion Battery Pack", "quantity": 1500, "warehouse": "Ordu-Hub", "reorder_threshold": 500},
        {"product_id": "P-002", "name": "Electric Motor 50kW", "quantity": 300, "warehouse": "Istanbul-Hub", "reorder_threshold": 100},
        {"product_id": "P-003", "name": "Brake Calipers Set", "quantity": 80, "warehouse": "Ankara-Hub", "reorder_threshold": 200}
    ]
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print("Loaded sc-inventory")

def load_shipments():
    table = dynamodb.Table('sc-shipments')
    items = [
        {"tracking_number": "TRK-12345", "status": "IN_TRANSIT", "origin": "Shanghai", "destination": "Ordu-Hub", "carrier": "Maersk", "eta": "2026-06-25"},
        {"tracking_number": "TRK-67890", "status": "DELAYED", "origin": "Taiwan", "destination": "Istanbul-Hub", "carrier": "FedEx", "eta": "2026-06-22", "delay_reason": "Customs Hold"},
        {"tracking_number": "TRK-11121", "status": "DELIVERED", "origin": "Ankara-Hub", "destination": "Ordu-Hub", "carrier": "DHL", "eta": "2026-06-19"}
    ]
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print("Loaded sc-shipments")

def load_routes():
    table = dynamodb.Table('sc-routes')
    items = [
        {"route_id": "RT-EU-01", "name": "Ankara to Ordu", "distance_km": 550, "estimated_hours": 6, "status": "CLEAR"},
        {"route_id": "RT-AS-EU-01", "name": "Shanghai to Istanbul Sea Route", "distance_km": 18000, "estimated_hours": 850, "status": "WEATHER_WARNING"}
    ]
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print("Loaded sc-routes")

def load_suppliers():
    table = dynamodb.Table('sc-suppliers')
    items = [
        {"supplier_id": "SUP-001", "name": "Global Tech Batteries", "rating": "A", "contact": "contact@gtb.com", "tier": 1},
        {"supplier_id": "SUP-002", "name": "FastMotors Inc", "rating": "B", "contact": "sales@fastmotors.com", "tier": 2},
        {"supplier_id": "SUP-003", "name": "Reliable Brakes Ltd", "rating": "A+", "contact": "support@reliablebrakes.com", "tier": 1}
    ]
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print("Loaded sc-suppliers")

def load_inspections():
    table = dynamodb.Table('sc-inspections')
    items = [
        {"batch_id": "BCH-1001", "product_id": "P-001", "inspector": "John Doe", "status": "PASSED", "date": "2026-06-18"},
        {"batch_id": "BCH-1002", "product_id": "P-002", "inspector": "Jane Smith", "status": "FAILED", "date": "2026-06-19", "reason": "Voltage variation exceeds 2%"}
    ]
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print("Loaded sc-inspections")

def load_compliance():
    table = dynamodb.Table('sc-compliance')
    items = [
        {"entity_id": "SUP-001", "entity_type": "SUPPLIER", "iso_9001": "VALID", "environmental_score": 92},
        {"entity_id": "P-001", "entity_type": "PRODUCT", "rohs_compliant": True, "ce_certified": True}
    ]
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print("Loaded sc-compliance")

def load_standards():
    table = dynamodb.Table('sc-standards')
    items = [
        {"category": "BATTERY", "max_voltage_variance_pct": 1.5, "required_certifications": ["ISO-9001", "CE", "UL"]},
        {"category": "MOTOR", "max_noise_db": 65, "required_certifications": ["ISO-9001", "CE"]}
    ]
    # Convert floats to Decimals for DynamoDB
    items = json.loads(json.dumps(items), parse_float=Decimal)
    
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print("Loaded sc-standards")

if __name__ == "__main__":
    print("Starting data load to DynamoDB...")
    try:
        load_inventory()
        load_shipments()
        load_routes()
        load_suppliers()
        load_inspections()
        load_compliance()
        load_standards()
        print("Successfully loaded all mock data!")
    except Exception as e:
        print(f"Error loading data: {e}")
