from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import logging
import boto3
from botocore.exceptions import NoCredentialsError
import time
app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
Base = declarative_base()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# Create a CloudWatch log client
try:
    log_client = boto3.client('logs', region_name="us-east-1")
except NoCredentialsError:
    logger.error("AWS credentials not found")

LOG_GROUP = '/my-fastapi-app/logs'
LOG_STREAM = os.getenv("INSTANCE_ID")

# Function to push logs to CloudWatch
import asyncio

async def push_logs_to_cloudwatch(log_message):
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None,  # Uses the default executor (which is a ThreadPoolExecutor)
            lambda: log_client.put_log_events(
                logGroupName=LOG_GROUP,
                logStreamName=LOG_STREAM,
                logEvents=[
                    {
                        'timestamp': int(round(time.time() * 1000)),
                        'message': log_message
                    },
                ],
            )
        )
    except Exception as e:
        logger.error(f"Error sending logs to CloudWatch: {e}")


class Item(Base):
    __tablename__ = 'items'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    description = Column(String(255), index=True)
SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(bind=engine)

@app.get("/healthcheck")
def healthcheck():
    return {"status": "ok"}

@app.post("/items/")
async def create_item(name: str, description: str):
    db = SessionLocal()
    new_item = Item(name=name, description=description)
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    await push_logs_to_cloudwatch(f"Create items with name {Item.name} and description {Item.description}")
    return new_item

@app.get("/items/")
async def read_items():
    db = SessionLocal()
    items = db.query(Item).all()
    await push_logs_to_cloudwatch(f"Read items, found {len(items)} items")
    return items

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    db = SessionLocal()
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    await push_logs_to_cloudwatch(f"Read item with id {item_id}")
    return item

@app.put("/items/{item_id}")
async def update_item(item_id: int, name: str, description: str):
    db = SessionLocal()
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    item.name = name
    item.description = description
    db.commit()
    await push_logs_to_cloudwatch(f"Update item with id {item_id}")
    return item

@app.delete("/items/{item_id}")
async def delete_item(item_id: int):
    db = SessionLocal()
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(item)
    db.commit()
    await push_logs_to_cloudwatch(f"Delete item with id {item_id}")
    return {"detail": "Item deleted successfully"}
