from datetime import datetime

import pandas as pd
from database.vector_store import VectorStore
from timescale_vector.client import uuid_from_time
import json

# Add a flag to control whether to drop existing tables
DROP_EXISTING_TABLES = True  # Set this to False if you want to keep existing tables

# Initialize VectorStore
vec = VectorStore()
vec.settings
# Instead of reading CSV, create DataFrame from the JSON
# If you have a JSON file:
with open("/home/artur/github/personal/OCR_learning/resp.json", 'r') as f:
    json_data = json.load(f)
    
# Convert single JSON document to a DataFrame with one row
df = pd.DataFrame([json_data])  # Note the square brackets to create a list with one item

vec.settings

# Prepare data for insertion
def prepare_record(row):
    """Prepare a record for insertion into the vector store from JSON document data."""
    # Combine relevant fields for embedding
    content_for_embedding = f"Sender: {row['sender']}\nAddressed to: {row['addressed_to']}\n{row['content_in_english']}"
    if row.get('required_actions'):
        for action in row['required_actions']:
            content_for_embedding += f"\nRequired Action: {action}"
    
    embedding = vec.get_embedding(content_for_embedding)
    
    # Prepare metadata (everything except content_in_english)
    metadata = {
        "title_in_original_language": row["title_in_original_language"],
        "title_in_english": row["title_in_english"],
        "sender": row["sender"],
        "sent_date": row["sent_date"],
        "addressed_to": row["addressed_to"],
        "content_in_original_language": row["content_in_original_language"],
        "summary_in_english": row["summary_in_english"],
        "required_actions": row["required_actions"]
    }

    return pd.Series({
        "id": str(uuid_from_time(datetime.now())),
        "metadata": metadata,
        "contents": content_for_embedding,
        "embedding": embedding,
    })


records_df = df.apply(prepare_record, axis=1)

# Create tables and insert data
if DROP_EXISTING_TABLES:
    vec.drop_tables()
vec.create_tables()
vec.create_index()  # DiskAnnIndex
vec.upsert(records_df)

    