#mapping_store.py
from pymongo import MongoClient
from datetime import datetime
import streamlit as st

def _get_collection():
    client = MongoClient(st.secrets["MONGO_URI"])
    db = client[st.secrets.get("MONGO_DB", "BDDWizard")]
    return db[st.secrets.get("MONGO_COLLECTION", "Mappings")]

def save_mapping(step_pattern, helper_chain, project="Default", source="manual", confidence=1.0):
    coll = _get_collection()
    doc = {
        "step_pattern": step_pattern,
        "project": project,
        "helper_chain": helper_chain,
        "created_on": datetime.utcnow().isoformat(),
        "source": source,
        "confidence": confidence
    }
    coll.update_one({"step_pattern": step_pattern}, {"$set": doc}, upsert=True)

def fetch_mappings(project="Default"):
    return list(_get_collection().find({"project": project}, {"_id": 0}))

def delete_mapping(step_pattern):
    _get_collection().delete_one({"step_pattern": step_pattern})

def find_mapping(step_text, project="Default"):
    mappings = fetch_mappings(project)
    for m in mappings:
        if step_text.lower() in m["step_pattern"].lower() or m["step_pattern"].lower() in step_text.lower():
            return m
    return None
