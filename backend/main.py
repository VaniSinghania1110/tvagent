import re
import random
import time
import os
import json
import urllib.request
import smtplib
import email.utils
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from pymongo import MongoClient, ReturnDocument
from dotenv import load_dotenv
from itinerary_ai import generate_professional_itinerary

# Auto-load .env configuration if present
_env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_file):
    load_dotenv(_env_file)
else:
    load_dotenv()

app = FastAPI(title="TravelVerse Backend API (MongoDB)")

# Enable CORS for frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["TravelVerse"]

def serialize_doc(doc):
    if not doc:
        return doc
    if isinstance(doc, list):
        return [serialize_doc(d) for d in doc]
    d = dict(doc)
    if "_id" in d:
        d["_id"] = str(d["_id"])
    return d

def get_next_sequence(sequence_name: str) -> int:
    ret = db.counters.find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return ret["seq"]

def sync_user_trip_interests_field(user_email: str):
    if not user_email:
        return
    try:
        email_clean = user_email.strip().lower()
        rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

        user = db.users.find_one({"$or": [{"email": rx}, {"username": rx}]})
        if not user:
            return

        u_email = (user.get("email") or "").strip().lower()
        u_uname = (user.get("username") or "").strip().lower()

        or_clauses = []
        if u_email:
            or_clauses.append({"user_email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}})
        if u_uname:
            or_clauses.append({"user_email": {"$regex": f"^{re.escape(u_uname)}$", "$options": "i"}})

        rows = []
        if or_clauses:
            rows = list(db.trip_interests.find({"$or": or_clauses}).sort("id", -1))

        interests = []
        seen_ids = set()
        for r in rows:
            d = serialize_doc(r)
            d.pop("_id", None)
            if d.get("id") not in seen_ids:
                seen_ids.add(d.get("id"))
                interests.append(d)

        db.users.update_many(
            {"$or": [{"email": rx}, {"username": rx}]},
            {"$set": {"trip_interests": interests}}
        )
    except Exception as e:
        print("User trip interests field sync note:", e)


def sync_all_users_trip_interests():
    try:
        db.users.update_many(
            {"trip_interests": {"$exists": False}},
            {"$set": {"trip_interests": []}}
        )
        users = list(db.users.find())
        for u in users:
            e = u.get("email") or u.get("username")
            if e:
                sync_user_trip_interests_field(e)
    except Exception as e:
        print("Sync all users trip interests note:", e)


def heal_group_trips_agent_info():
    try:
        agents_map = {}
        for a in db.agents.find():
            if "id" in a:
                try: agents_map[int(a["id"])] = a
                except: pass
        for t in db.group_trips.find():
            aid = t.get("agent_id")
            if aid:
                try: aid_int = int(aid)
                except: aid_int = None
                if aid_int and aid_int in agents_map:
                    ag = agents_map[aid_int]
                    updates = {}
                    if not t.get("agent_email") and ag.get("email"):
                        updates["agent_email"] = ag["email"].strip().lower()
                    if not t.get("agent_name") and ag.get("agent_name"):
                        updates["agent_name"] = ag["agent_name"].strip()
                    if not t.get("agency_name") and ag.get("agency_name"):
                        updates["agency_name"] = ag["agency_name"].strip()
                    if updates:
                        db.group_trips.update_one({"_id": t["_id"]}, {"$set": updates})
    except Exception as e:
        print("Heal group trips note:", e)

def init_mongo_db():
    try:
        client.admin.command("ping")
        print("MongoDB connected successfully to TravelVerse database!")
        # Create indexes for search and uniqueness
        db.users.create_index("email", unique=True)
        db.users.create_index("username", unique=True)
        db.travellers.create_index("email", unique=True)
        db.travellers.create_index("username", unique=True)
        db.companions.create_index("id", unique=True)
        db.reviews.create_index("companion_id")
        db.agents.create_index("id", unique=True)
        db.agents.create_index("email")
        db.trip_interests.create_index("user_email")
        db.connections.create_index([("sender_email", 1), ("receiver_email", 1)])
        db.group_trips.create_index("id", unique=True)
        db.group_trips.create_index("agent_email")
        db.trip_enrollments.create_index("id", unique=True)
        db.trip_enrollments.create_index("user_email")
        db.trip_enrollments.create_index("agent_email")
        db.agent_inquiries.create_index("id", unique=True)
        db.agent_inquiries.create_index("agent_email")
        db.queries.create_index("id", unique=True)
        db.queries.create_index("agent_email")
        db.queries.create_index("trip_id")
        db.bookings.create_index("id", unique=True)
        db.bookings.create_index("trip_id")
        db.bookings.create_index("agent_email")
        db.bookings.create_index("user_email")
        db.trip_messages.create_index("id", unique=True)
        db.trip_messages.create_index("trip_id")
        sync_all_users_trip_interests()
        seed_default_agents_and_trips()
        heal_group_trips_agent_info()
        sync_travellers_and_agents_collections()
        sync_queries_and_bookings_collections()
    except Exception as e:
        print("MongoDB connection warning:", e)


def seed_default_agents_and_trips():
    try:
        if db.agents.count_documents({}) == 0:
            seed_agents = [
                {
                    "id": 1,
                    "agent_type": "person",
                    "agent_name": "Aarav Sharma",
                    "agency_name": "Himalayan High Passes",
                    "email": "aarav.sharma@travelverse.com",
                    "phone": "+91 98765 43210",
                    "rating": 4.98,
                    "reviews_count": 64,
                    "specialty": "High-Altitude Passes, Spiti & Ladakh 4x4",
                    "destinations": "Spiti Valley, Ladakh, Manali, Zanskar, Nepal",
                    "bio": "Certified mountaineer and wilderness first responder with 8+ years leading offbeat 4x4 road journeys and high-altitude treks across the Western Himalayas.",
                    "experience_years": 8,
                    "languages": "English, Hindi, Pahadi",
                    "profile_pic": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&q=80",
                    "badges": ["Certified Mountaineer", "Wilderness First Aid", "Top Rated Guide"],
                    "verified": 1,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "id": 2,
                    "agent_type": "person",
                    "agent_name": "Elena Rostova",
                    "agency_name": "Arctic & Alpine Trailblazer",
                    "email": "elena.rostova@travelverse.com",
                    "phone": "+41 78 123 4567",
                    "rating": 4.96,
                    "reviews_count": 52,
                    "specialty": "Aurora Chasing, Glacier Treks & Alpine Hikes",
                    "destinations": "Iceland, Swiss Alps, Norway, Dolomites",
                    "bio": "Glacier expedition leader and landscape photographer. I take small groups off the tourist track to witness northern lights and secret alpine viewpoints.",
                    "experience_years": 9,
                    "languages": "English, German, Russian",
                    "profile_pic": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=400&q=80",
                    "badges": ["Glacier Guide", "Photo Expedition Leader"],
                    "verified": 1,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "id": 3,
                    "agent_type": "person",
                    "agent_name": "Mateo Silva",
                    "agency_name": "Andes & Inca Cultural Treks",
                    "email": "mateo.silva@travelverse.com",
                    "phone": "+51 984 567 890",
                    "rating": 4.93,
                    "reviews_count": 39,
                    "specialty": "Inca Trail, Sacred Valley & Andean Gastronomy",
                    "destinations": "Cusco, Machu Picchu, Rainbow Mountain, Peru",
                    "bio": "Born and raised in Cusco, licensed Quechua-speaking heritage guide passionate about ancient Inca engineering, sustainable hiking, and authentic village home-stays.",
                    "experience_years": 7,
                    "languages": "English, Spanish, Quechua",
                    "profile_pic": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=400&q=80",
                    "badges": ["Licensed Heritage Guide", "Local Native Host"],
                    "verified": 1,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "id": 4,
                    "agent_type": "group",
                    "agent_name": "Vikram & Nomad Crew",
                    "agency_name": "Nomad Trails Expeditions",
                    "email": "contact@nomadtrails.org",
                    "phone": "+91 91234 56780",
                    "rating": 4.95,
                    "reviews_count": 118,
                    "specialty": "Overland Expeditions, Heritage Rallies & Silk Road",
                    "destinations": "Rajasthan, Central Asia, Spiti, Georgia, Vietnam",
                    "bio": "A premier collective of expedition leaders, mechanics, and local storytellers specializing in self-drive convoys, desert camp-outs, and deep cultural immersion.",
                    "experience_years": 12,
                    "languages": "English, Hindi, French",
                    "profile_pic": "https://images.unsplash.com/photo-1539635278303-d4002c07eae3?auto=format&fit=crop&w=400&q=80",
                    "badges": ["Govt. Registered Operator", "24/7 Road Support"],
                    "verified": 1,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "id": 5,
                    "agent_type": "group",
                    "agent_name": "Sophia Laurent",
                    "agency_name": "Odyssey Luxury Voyages",
                    "email": "concierge@odysseyvoyages.com",
                    "phone": "+33 1 42 68 55 00",
                    "rating": 4.97,
                    "reviews_count": 87,
                    "specialty": "Bespoke Island Escapes, Yacht Charters & Wine Tours",
                    "destinations": "Amalfi Coast, Santorini, Bali, French Riviera, Maldives",
                    "bio": "Award-winning boutique luxury travel agency curating five-star private villa retreats, catamaran sails, wine-tasting journeys, and VIP concierge experiences.",
                    "experience_years": 14,
                    "languages": "English, French, Italian",
                    "profile_pic": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=400&q=80",
                    "badges": ["Virtuoso Partner", "VIP Concierge"],
                    "verified": 1,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "id": 6,
                    "agent_type": "group",
                    "agent_name": "Kipchoge Mwangi & Team",
                    "agency_name": "Safari & Savannah Collective",
                    "email": "info@savannahcollective.co.ke",
                    "phone": "+254 700 123 456",
                    "rating": 4.94,
                    "reviews_count": 96,
                    "specialty": "Big 5 Game Drives, Great Migration & Eco-Lodges",
                    "destinations": "Masai Mara, Serengeti, Amboseli, Ngorongoro",
                    "bio": "Native East African conservationists and professional safari guides offering ethical game drives, sunrise balloon safaris, and luxury tented wilderness camps.",
                    "experience_years": 11,
                    "languages": "English, Swahili",
                    "profile_pic": "https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?auto=format&fit=crop&w=400&q=80",
                    "badges": ["Eco-Tourism Gold", "Certified Wildlife Guide"],
                    "verified": 1,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            ]
            db.agents.insert_many(seed_agents)
            for a in seed_agents:
                u_email = a["email"].strip().lower()
                if not db.users.find_one({"email": u_email}):
                    db.users.insert_one({
                        "id": get_next_sequence("users"),
                        "first_name": a["agent_name"].split()[0],
                        "last_name": " ".join(a["agent_name"].split()[1:]) or "Agent",
                        "username": a["agent_name"].lower().replace(" ", "_").replace("&", "and"),
                        "email": u_email,
                        "password": "agentpassword123",
                        "role": "agent",
                        "agent_id": a["id"],
                        "agency_name": a["agency_name"],
                        "badges": a.get("badges", []),
                        "profile_pic": a.get("profile_pic", ""),
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
        for a in db.agents.find():
            u_email = (a.get("email") or "").strip().lower()
            if u_email and not db.users.find_one({"email": u_email}):
                db.users.insert_one({
                    "id": get_next_sequence("users"),
                    "first_name": a["agent_name"].split()[0],
                    "last_name": " ".join(a["agent_name"].split()[1:]) or "Agent",
                    "username": a["agent_name"].lower().replace(" ", "_").replace("&", "and"),
                    "email": u_email,
                    "password": "agentpassword123",
                    "role": "agent",
                    "agent_id": a["id"],
                    "agency_name": a.get("agency_name", ""),
                    "badges": a.get("badges", []),
                    "profile_pic": a.get("profile_pic", ""),
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                })

        # Sync any travellers in db.travellers into db.users
        for t in db.travellers.find():
            u_email = (t.get("email") or "").strip().lower()
            if u_email:
                rx_t = {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}
                if not db.users.find_one({"email": rx_t}):
                    u_doc = {
                        "id": t.get("id") or get_next_sequence("users"),
                        "first_name": t.get("first_name", "Traveller"),
                        "last_name": t.get("last_name", ""),
                        "username": t.get("username", u_email.split("@")[0]),
                        "email": u_email,
                        "password": t.get("password", "password123"),
                        "role": "traveller",
                        "badges": t.get("badges", ["🎒 Backpacker"]),
                        "trip_interests": t.get("trip_interests", []),
                        "profile_pic": t.get("profile_pic", ""),
                        "created_at": t.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
                    }
                    db.users.insert_one(u_doc)

        if db.group_trips.count_documents({}) == 0:
            seed_trips = [
                {
                    "id": 101,
                    "agent_id": 1,
                    "agent_name": "Aarav Sharma",
                    "agent_type": "person",
                    "agent_email": "aarav.sharma@travelverse.com",
                    "agent_phone": "+91 98765 43210",
                    "title": "Spiti Valley 4x4 High-Altitude Expedition",
                    "destination": "Spiti Valley & Kaza, India",
                    "category": "Adventure",
                    "start_date": "2026-11-20",
                    "end_date": "2026-11-28",
                    "duration_days": 8,
                    "price": 690,
                    "currency": "USD",
                    "max_capacity": 10,
                    "enrolled_count": 6,
                    "cover_image": "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=800&q=80",
                    "description": "Traverse high mountain passes, suspension bridges, ancient monasteries, and camp under milky way skies at Chandratal lake.",
                    "inclusions": ["4x4 Expedition Vehicle", "All Homestays & Tents", "Permits & Oxygen", "Breakfast & Dinner"],
                    "exclusions": ["Airfare to Manali", "Personal Gear"],
                    "difficulty": "Challenging",
                    "meeting_point": "Old Manali Clubhouse, 8:00 AM",
                    "status": "active",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "id": 102,
                    "agent_id": 2,
                    "agent_name": "Elena Rostova",
                    "agent_type": "person",
                    "agent_email": "elena.rostova@travelverse.com",
                    "agent_phone": "+41 78 123 4567",
                    "title": "Iceland Northern Lights & Crystal Ice Caves",
                    "destination": "Reykjavik, Vik & Vatnajökull, Iceland",
                    "category": "Glacier & Aurora",
                    "start_date": "2026-12-05",
                    "end_date": "2026-12-12",
                    "duration_days": 7,
                    "price": 1450,
                    "currency": "USD",
                    "max_capacity": 8,
                    "enrolled_count": 5,
                    "cover_image": "https://images.unsplash.com/photo-1517411032315-54ef2cb783bb?auto=format&fit=crop&w=800&q=80",
                    "description": "Explore natural blue ice caves, black sand beaches, geothermal hot pools, and hunt the Aurora Borealis every clear night.",
                    "inclusions": ["Super Jeep Transport", "Boutique Lodges", "Glacier Crampons & Helmets", "Aurora Photo Guide"],
                    "exclusions": ["International Flights", "Lunches & Alcoholic Beverages"],
                    "difficulty": "Moderate",
                    "meeting_point": "Reykjavik City Center, 9:00 AM",
                    "status": "active",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "id": 103,
                    "agent_id": 3,
                    "agent_name": "Mateo Silva",
                    "agent_type": "person",
                    "agent_email": "mateo.silva@travelverse.com",
                    "agent_phone": "+51 984 567 890",
                    "title": "Machu Picchu & Sacred Valley Cultural Trek",
                    "destination": "Cusco & Machu Picchu, Peru",
                    "category": "Cultural",
                    "start_date": "2027-01-12",
                    "end_date": "2027-01-18",
                    "duration_days": 6,
                    "price": 920,
                    "currency": "USD",
                    "max_capacity": 12,
                    "enrolled_count": 7,
                    "cover_image": "https://images.unsplash.com/photo-1526392060635-9d6019884377?auto=format&fit=crop&w=800&q=80",
                    "description": "Hike the Inca Trail with a native Quechua historian, experience authentic Andean feasts, and watch sunrise hit the Sun Gate.",
                    "inclusions": ["Inca Trail Permits", "Porters & Chefs", "Camping Equipment", "Machu Picchu Entry & Train"],
                    "exclusions": ["Flights to Cusco", "Travel Insurance", "Tips for Porters"],
                    "difficulty": "Moderate",
                    "meeting_point": "Plaza de Armas Cusco, 6:00 AM",
                    "status": "active",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "id": 104,
                    "agent_id": 5,
                    "agent_name": "Odyssey Luxury Voyages",
                    "agent_type": "group",
                    "agent_email": "concierge@odysseyvoyages.com",
                    "agent_phone": "+33 1 42 68 55 00",
                    "title": "Bali & Nusa Penida Wellness & Island Sail",
                    "destination": "Ubud & Nusa Penida, Bali",
                    "category": "Island & Luxury",
                    "start_date": "2026-11-25",
                    "end_date": "2026-12-02",
                    "duration_days": 7,
                    "price": 1280,
                    "currency": "USD",
                    "max_capacity": 14,
                    "enrolled_count": 9,
                    "cover_image": "https://images.unsplash.com/photo-1537996194471-e657df975ab4?auto=format&fit=crop&w=800&q=80",
                    "description": "Private catamaran charter to Manta Bay, jungle infinity villa stays, sound healing therapy, and beachside sunset dinners.",
                    "inclusions": ["5-Star Jungle Villa", "Private Catamaran Charter", "All Organic Meals", "Spa & Yoga Sessions"],
                    "exclusions": ["Airfare to Denpasar (DPS)", "Personal Shopping"],
                    "difficulty": "Easy",
                    "meeting_point": "Ubud Valley Resort Lobby, 12:00 PM",
                    "status": "active",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                },
                {
                    "id": 105,
                    "agent_id": 6,
                    "agent_name": "Safari & Savannah Collective",
                    "agent_type": "group",
                    "agent_email": "info@savannahcollective.co.ke",
                    "agent_phone": "+254 700 123 456",
                    "title": "Great Serengeti & Masai Mara Big 5 Safari",
                    "destination": "Masai Mara & Serengeti, Kenya",
                    "category": "Safari",
                    "start_date": "2026-12-15",
                    "end_date": "2026-12-23",
                    "duration_days": 8,
                    "price": 2100,
                    "currency": "USD",
                    "max_capacity": 10,
                    "enrolled_count": 6,
                    "cover_image": "https://images.unsplash.com/photo-1516426122078-c23e76319801?auto=format&fit=crop&w=800&q=80",
                    "description": "Witness the Great Migration, sunrise hot air balloon flight over the Mara, and stay in luxury eco-tented wilderness camps.",
                    "inclusions": ["Custom 4x4 Land Cruisers", "Luxury Tented Lodges", "Park Conservation Fees", "Hot Air Balloon Flight"],
                    "exclusions": ["International Airfare", "Visa Fees", "Alcoholic Beverages"],
                    "difficulty": "Easy",
                    "meeting_point": "Nairobi Wilson Airport, 7:00 AM",
                    "status": "active",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            ]
            db.group_trips.insert_many(seed_trips)
            print(f"Seeded {len(seed_trips)} default group trips into TravelVerse.")
    except Exception as e:
        print("Seeding note:", e)

# Request Models

def sync_travellers_and_agents_collections():
    """
    Ensures travellers' info is populated strictly in db.travellers,
    and registered agents' info is populated strictly in db.agents.
    Ensures no overlap or cross-contamination between travellers and agents tables.
    """
    try:
        # 1. Ensure all agents in db.agents have role = "agent"
        db.agents.update_many({"role": {"$ne": "agent"}}, {"$set": {"role": "agent"}})

        # Collect all agent emails
        agent_emails = set()
        for a in db.agents.find({}, {"email": 1}):
            em = (a.get("email") or "").strip().lower()
            if em:
                agent_emails.add(em)

        # 2. Sync agents from db.users where role == "agent"
        agent_users = list(db.users.find({"role": "agent"}))
        for u in agent_users:
            u_email = (u.get("email") or "").strip().lower()
            if u_email:
                agent_emails.add(u_email)
                db.agents.update_one(
                    {"email": u_email},
                    {"$set": {
                        "password": u.get("password", ""),
                        "username": u.get("username", ""),
                        "agency_name": u.get("agency_name", ""),
                        "role": "agent"
                    }},
                    upsert=True
                )

        # 3. Remove all agent accounts from db.travellers (so travellers table contains ONLY travellers)
        for em in agent_emails:
            db.travellers.delete_many({"email": {"$regex": f"^{re.escape(em)}$", "$options": "i"}})

        # 4. Sync travellers from db.users where role != "agent" and email NOT in agent_emails
        traveller_users = list(db.users.find({"role": {"$ne": "agent"}}))
        for u in traveller_users:
            u_email = (u.get("email") or "").strip().lower()
            if not u_email or u_email in agent_emails:
                continue
            doc = serialize_doc(u)
            doc.pop("_id", None)
            doc["role"] = "traveller"
            db.travellers.update_one(
                {"email": u_email},
                {"$set": doc},
                upsert=True
            )
            # Ensure traveller is not in agents table
            db.agents.delete_many({"email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}})

        # 5. Ensure all documents in db.travellers have role = "traveller"
        db.travellers.update_many({"role": {"$ne": "traveller"}}, {"$set": {"role": "traveller"}})

    except Exception as e:
        print("Note on travellers/agents sync:", e)

def sync_queries_and_bookings_collections():
    """
    Synchronizes agent_inquiries with queries table, and trip_enrollments with bookings table,
    ensuring MongoDB queries and bookings collections are always 100% aligned.
    """
    try:
        # Sync agent_inquiries <-> queries
        for inq in db.agent_inquiries.find({}):
            doc = dict(inq)
            doc.pop("_id", None)
            db.queries.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
        for q in db.queries.find({}):
            doc = dict(q)
            doc.pop("_id", None)
            db.agent_inquiries.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)

        # Sync trip_enrollments <-> bookings
        for enr in db.trip_enrollments.find({}):
            doc = dict(enr)
            doc.pop("_id", None)
            db.bookings.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
        for b in db.bookings.find({}):
            doc = dict(b)
            doc.pop("_id", None)
            db.trip_enrollments.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
    except Exception as e:
        print("Note on queries/bookings sync:", e)

init_mongo_db()


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    username: str
    email: str
    password: str
    role: Optional[str] = "traveller" # "traveller" or "agent"
    badges: Optional[List[str]] = []
    # Agent-specific fields
    agency_name: Optional[str] = ""
    agent_name: Optional[str] = ""
    agent_type: Optional[str] = "person" # "person" or "group"
    phone: Optional[str] = ""
    specialty: Optional[str] = ""
    destinations: Optional[str] = ""
    experience_years: Optional[int] = 3
    languages: Optional[str] = "English"
    bio: Optional[str] = ""
    profile_pic: Optional[str] = ""

class LoginRequest(BaseModel):
    email_or_username: str
    password: str
    expected_role: Optional[str] = None # "traveller" or "agent" or None


class SendOTPRequest(BaseModel):
    email: str

class VerifyOTPRequest(BaseModel):
    email: str
    otp: str

class SendSignupOTPRequest(BaseModel):
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    username: Optional[str] = ""
    email: str
    password: Optional[str] = ""

class VerifySignupOTPRequest(BaseModel):
    email: str
    otp: str

class SendEmailOTPOnlyRequest(BaseModel):
    email: str

class VerifyEmailOTPOnlyRequest(BaseModel):
    email: str
    otp: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str

class VerifyOTPResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str

class UpdateUsernameRequest(BaseModel):
    email: str
    new_username: str

class UpdateBadgesRequest(BaseModel):
    email: str
    badges: List[str]

class DeleteAccountRequest(BaseModel):
    email: str

class ConnectionRequestModel(BaseModel):
    sender_email: str
    receiver_email: str
    message: Optional[str] = ""

class RespondConnectionRequest(BaseModel):
    connection_id: int
    user_email: str
    status: str

class WithdrawConnectionRequest(BaseModel):
    connection_id: Optional[int] = 0
    sender_email: Optional[str] = ""
    receiver_email: Optional[str] = ""


class CreateCompanionRequest(BaseModel):
    user_name: str
    user_email: str
    username: str
    destination: str
    dates: str
    budget: str
    pace: str
    badges: List[str]
    bio: str
    profile_pic: Optional[str] = ""

class ConnectCompanionRequest(BaseModel):
    sender_email: str
    sender_name: str
    companion_id: int
    message: str

class AddReviewRequest(BaseModel):
    companion_id: int
    reviewer_name: str
    reviewer_email: str
    rating: float
    review_text: str

class RegisterAgentRequest(BaseModel):
    agency_name: Optional[str] = ""
    agent_name: str
    email: str
    password: Optional[str] = ""
    username: Optional[str] = ""
    specialty: Optional[str] = ""
    destinations: Optional[str] = ""
    profile_pic: Optional[str] = ""
    agent_type: Optional[str] = "person"  # "person" or "group"
    phone: Optional[str] = ""
    bio: Optional[str] = ""
    experience_years: Optional[int] = 3
    languages: Optional[str] = "English"
    cover_image: Optional[str] = ""
    badges: Optional[List[str]] = []

class UpdateAgentProfileRequest(BaseModel):
    email: str
    agent_name: Optional[str] = None
    agency_name: Optional[str] = None
    agent_type: Optional[str] = None
    phone: Optional[str] = None
    specialty: Optional[str] = None
    destinations: Optional[str] = None
    experience_years: Optional[int] = None
    languages: Optional[str] = None
    bio: Optional[str] = None
    profile_pic: Optional[str] = None
    badges: Optional[List[str]] = None

class AIGenerateItineraryRequest(BaseModel):
    destination: str
    duration_days: Optional[int] = 5
    category: Optional[str] = "Cultural"
    difficulty: Optional[str] = "Moderate"
    agent_name: Optional[str] = "Host Guide"
    agency_name: Optional[str] = "Travel Agency"

class CreateGroupTripRequest(BaseModel):
    agent_id: Optional[int] = 0
    agent_name: str
    agent_type: Optional[str] = "person"
    agency_name: Optional[str] = ""
    agent_email: Optional[str] = ""
    agent_phone: Optional[str] = ""
    title: str
    destination: str
    tagline: Optional[str] = ""
    season_climate: Optional[str] = ""
    min_age: Optional[str] = "10+"
    stay_type: Optional[str] = ""
    transit_mode: Optional[str] = ""
    packing_essentials: Optional[List[str]] = []
    dropoff_point: Optional[str] = ""
    health_advisory: Optional[str] = ""
    category: Optional[str] = "Adventure"
    start_date: str
    end_date: Optional[str] = ""
    duration_days: Optional[int] = 7
    price: float
    currency: Optional[str] = "USD"
    max_capacity: int
    enrolled_count: Optional[int] = 0
    cover_image: Optional[str] = ""
    description: Optional[str] = ""
    highlights: Optional[List[str]] = []
    itinerary: Optional[List[dict]] = []
    inclusions: Optional[List[str]] = []
    exclusions: Optional[List[str]] = []
    difficulty: Optional[str] = "Moderate"
    meeting_point: Optional[str] = ""

class EditGroupTripRequest(BaseModel):
    id: int
    agent_email: Optional[str] = ""
    title: Optional[str] = None
    destination: Optional[str] = None
    category: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_days: Optional[int] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    max_capacity: Optional[int] = None
    cover_image: Optional[str] = None
    description: Optional[str] = None
    inclusions: Optional[List[str]] = None
    exclusions: Optional[List[str]] = None
    difficulty: Optional[str] = None
    meeting_point: Optional[str] = None
    status: Optional[str] = None

class EnrollGroupTripRequest(BaseModel):
    trip_id: int
    user_email: str
    user_name: str
    user_phone: Optional[str] = ""
    seats: Optional[int] = 1
    traveller_names: Optional[List[str]] = []
    special_notes: Optional[str] = ""

class CancelEnrollmentRequest(BaseModel):
    enrollment_id: Optional[int] = None
    booking_code: Optional[str] = None
    user_email: str

class ContactAgentRequest(BaseModel):
    agent_id: Optional[int] = 0
    agent_name: Optional[str] = ""
    agent_email: Optional[str] = ""
    user_email: str
    user_name: str
    user_phone: Optional[str] = ""
    inquiry_type: Optional[str] = "general"
    reason: Optional[str] = None
    trip_id: Optional[int] = None
    trip_title: Optional[str] = ""
    destination: Optional[str] = ""
    travel_dates: Optional[str] = ""
    expected_dates: Optional[str] = None
    budget: Optional[str] = ""
    group_size: Optional[str] = "1"
    message: Optional[str] = ""
    message_text: Optional[str] = None

class SendTripMessageRequest(BaseModel):
    trip_id: int
    sender_email: str
    sender_name: Optional[str] = "Host Guide"
    sender_role: Optional[str] = "agent"
    message_text: str

class UpdateInquiryStatusRequest(BaseModel):
    inquiry_id: int
    status: str # "pending", "contacted", "confirmed"

class UpdateBookingStatusRequest(BaseModel):
    booking_code: Optional[str] = None
    enrollment_id: Optional[int] = None
    status: str # "confirmed", "unconfirmed", "cancelled", "pending"
    agent_email: Optional[str] = None
    agent_name: Optional[str] = None
    note: Optional[str] = None


class AnswerQueryRequest(BaseModel):
    inquiry_id: int
    reply_text: str
    agent_email: str = ""
    agent_name: str = ""


class AddTripInterestRequest(BaseModel):
    user_email: str
    destination: str
    preferred_dates: str
    budget: Optional[str] = ""
    notes: Optional[str] = ""

class EditTripInterestRequest(BaseModel):
    id: int
    user_email: str
    destination: str
    preferred_dates: str
    budget: Optional[str] = ""
    notes: Optional[str] = ""

class DeleteTripInterestRequest(BaseModel):
    id: int
    user_email: str


def send_real_email_otp(to_email: str, otp_code: str, is_signup: bool = False) -> bool:
    """
    Sends real OTP email to user's email address using SMTP or EmailJS REST API.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").replace(" ", "").strip()

    title_text = "Verify Your Email Address" if is_signup else "Reset Your Password"
    sub_text = "Welcome to TravelVerse! Enter the verification code below to verify your email and activate your account:" if is_signup else "Use the verification code below or click the button to reset your password directly:"
    subject_line = f"Verify Your TravelVerse Account: {otp_code}" if is_signup else f"Your TravelVerse Verification Code: {otp_code}"

    direct_link = f"http://127.0.0.1:5500/TravelVerse/frontend/login.html?reset_email={urllib.parse.quote(to_email)}&code={otp_code}"
    button_html = "" if is_signup else f'<a href="{direct_link}" class="btn">Reset Password Directly →</a>'

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #F4EEE2; margin: 0; padding: 20px; }}
        .card {{ max-width: 480px; margin: 0 auto; background: #FFFDF8; border-radius: 16px; padding: 32px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); border: 1px solid rgba(23,36,42,0.1); }}
        .header {{ text-align: center; margin-bottom: 24px; }}
        .logo {{ font-size: 24px; font-weight: 700; color: #0B2027; text-decoration: none; }}
        .otp-box {{ background: #0B2027; color: #E8874A; font-size: 36px; font-weight: 800; letter-spacing: 8px; text-align: center; padding: 18px; border-radius: 12px; margin: 24px 0 16px 0; }}
        .btn {{ display: block; background: #E8874A; color: #FFFFFF !important; text-decoration: none; font-weight: 700; font-size: 15px; text-align: center; padding: 14px 24px; border-radius: 10px; margin: 18px 0; }}
        .sub {{ font-size: 14px; color: #55625F; line-height: 1.6; text-align: center; }}
        .footer {{ margin-top: 24px; font-size: 12px; color: #888; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <div class="logo">✈️ TravelVerse</div>
        </div>
        <h2 style="color: #17242A; margin-top: 0; text-align: center;">{title_text}</h2>
        <p class="sub">{sub_text}</p>
        <div class="otp-box">{otp_code}</div>
        {button_html}
        <p class="sub">This code is valid for 10 minutes. If you did not request this code, please ignore this email.</p>
        <div class="footer">
          &copy; TravelVerse Security Notification
        </div>
      </div>
    </body>
    </html>
    """

    email_sent = False

    if smtp_user and smtp_pass:
        try:
            plain_text = f"Your TravelVerse verification code is: {otp_code}\n\n{sub_text}\n\nThis code is valid for 10 minutes. If you did not request this code, please ignore this email."

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject_line
            msg["From"] = f"TravelVerse <{smtp_user}>"
            msg["To"] = to_email
            msg["Reply-To"] = smtp_user
            msg["Date"] = email.utils.formatdate(localtime=True)
            msg["Message-ID"] = email.utils.make_msgid(domain="gmail.com")
            msg["X-Mailer"] = "TravelVerse Security Dispatcher"

            msg.attach(MIMEText(plain_text, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, to_email, msg.as_string())
            print(f"[SUCCESS] REAL OTP EMAIL SENT via SMTP to {to_email}")
            email_sent = True
        except Exception as e:
            print(f"[WARNING] SMTP Send Error: {e}")

    emailjs_user = os.getenv("EMAILJS_PUBLIC_KEY", "")
    if not email_sent and emailjs_user:
        try:
            url = "https://api.emailjs.com/api/v1.0/email/send"
            payload = {
                "service_id": os.getenv("EMAILJS_SERVICE_ID", "service_travelverse"),
                "template_id": os.getenv("EMAILJS_TEMPLATE_ID", "template_travelverse"),
                "user_id": emailjs_user,
                "template_params": {
                    "to_email": to_email,
                    "otp_code": otp_code,
                    "message": f"Your TravelVerse password reset OTP is: {otp_code}"
                }
            }
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    print(f"[SUCCESS] REAL OTP EMAIL SENT via EmailJS to {to_email}")
                    email_sent = True
        except Exception as e:
            print(f"[WARNING] EmailJS dispatch note: {e}")

    print(f"[SECURITY DISPATCH] OTP Code for {to_email}: {otp_code}")
    return email_sent


def send_booking_confirmation_email(
    booking_doc: dict,
    trip_doc: Optional[dict] = None,
    agent_doc: Optional[dict] = None,
    agent_email: Optional[str] = None,
    agent_name: Optional[str] = None,
    agent_note: Optional[str] = None
) -> dict:
    """
    Sends an official Travel Confirmation Letter & Voucher to the traveller's email address
    from the host agent via SMTP. Contains trip parameters, inclusions, rendezvous,
    and a 'View More Details' button directing back to the hosted trip page.
    """
    to_email = (booking_doc.get("user_email") or "").strip()
    if not to_email:
        return {"success": False, "detail": "Traveller email is missing on booking record."}

    user_name = booking_doc.get("user_name") or "Valued Traveller"
    booking_code = booking_doc.get("booking_code") or f"TV-BK-{booking_doc.get('id', 101)}"
    seats = int(booking_doc.get("seats") or 1)

    traveller_names = booking_doc.get("traveller_names")
    if isinstance(traveller_names, list) and traveller_names:
        passengers_str = ", ".join(traveller_names)
    elif isinstance(traveller_names, str) and traveller_names.strip():
        passengers_str = traveller_names.strip()
    else:
        passengers_str = user_name

    trip_id = booking_doc.get("trip_id")
    if not trip_doc and trip_id is not None:
        trip_doc = db.group_trips.find_one({"$or": [{"id": trip_id}, {"id": str(trip_id)}]})

    # Resolve agent details
    if not agent_doc and agent_email:
        agent_doc = db.agents.find_one({"email": {"$regex": f"^{re.escape(agent_email.strip())}$", "$options": "i"}})
    if not agent_doc and trip_doc and trip_doc.get("agent_email"):
        agent_doc = db.agents.find_one({"email": {"$regex": f"^{re.escape(trip_doc['agent_email'].strip())}$", "$options": "i"}})

    host_name = (
        agent_name
        or (agent_doc.get("agent_name") if agent_doc else None)
        or booking_doc.get("agent_name")
        or (trip_doc.get("agent_name") if trip_doc else None)
        or "TravelVerse Host Agent"
    )
    host_email = (
        agent_email
        or (agent_doc.get("email") if agent_doc else None)
        or booking_doc.get("agent_email")
        or (trip_doc.get("agent_email") if trip_doc else None)
        or os.getenv("SMTP_USER", "chitrakshgupta21@gmail.com")
    ).strip()
    agency = (
        (agent_doc.get("agency_name") or agent_doc.get("company_name")) if agent_doc
        else (trip_doc.get("agency_name") if trip_doc else "")
    )
    host_phone = (
        (agent_doc.get("phone") or agent_doc.get("whatsapp")) if agent_doc
        else (booking_doc.get("user_phone") or "")
    )

    # Trip details
    trip_title = (trip_doc.get("title") if trip_doc else None) or booking_doc.get("trip_title") or "Hosted Departure"
    destination = (trip_doc.get("destination") if trip_doc else None) or booking_doc.get("destination") or "Scenic Destination"
    start_date = (trip_doc.get("start_date") if trip_doc else None) or booking_doc.get("start_date") or "Upcoming Schedule"
    duration_days = (trip_doc.get("duration_days") if trip_doc else None) or booking_doc.get("duration_days") or 7
    unit_price = int(trip_doc.get("price") if trip_doc else (booking_doc.get("price") or 0))
    currency = (trip_doc.get("currency") if trip_doc else None) or booking_doc.get("currency") or "USD"
    total_price = unit_price * seats
    meeting_point = (trip_doc.get("meeting_point") if trip_doc else None) or "Detailed meeting coordinates provided upon departure briefing"

    inclusions = (trip_doc.get("inclusions") if trip_doc else None) or [
        "Certified professional host & expedition guide",
        "Dedicated group transportation & driver logistics",
        "All required wilderness permits and regional entry fees",
        "Curated daily itinerary and group coordination"
    ]
    exclusions = (trip_doc.get("exclusions") if trip_doc else None) or [
        "Personal travel insurance & medical coverage",
        "Airfare / individual transit to rendezvous point",
        "Discretionary personal expenses and optional activities"
    ]
    notes = booking_doc.get("special_notes") or agent_note or "Standard approved reservation"

    # Deep link to hosted trip & streaming PDF brochure
    app_base = os.getenv("APP_URL", "http://127.0.0.1:8000").rstrip("/")
    pdf_details_url = f"{app_base}/trip-itinerary.pdf?trip_id={trip_id}&booking_code={booking_code}" if trip_id else f"{app_base}/trip-itinerary.pdf"
    view_details_url = f"{app_base}/trip-itinerary.html?trip_id={trip_id}&booking_code={booking_code}" if trip_id else f"{app_base}/trip-itinerary.html"

    inclusions_html = "".join([f"<li style='padding:4px 0; color:#166534;'>✓ {inc}</li>" for inc in inclusions])
    exclusions_html = "".join([f"<li style='padding:4px 0; color:#991B1B;'>✕ {exc}</li>" for exc in exclusions])
    issue_date = time.strftime("%B %d, %Y")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Booking Confirmation Letter - TravelVerse</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F4EEE2; margin: 0; padding: 24px 12px; color: #17242A; }}
    .email-card {{ max-width: 620px; margin: 0 auto; background: #FFFFFF; border-radius: 18px; overflow: hidden; box-shadow: 0 10px 30px rgba(23,36,42,0.08); border: 1px solid rgba(23,36,42,0.1); }}
    .header {{ background: #0B2027; padding: 28px 24px; text-align: center; color: #FFFFFF; border-bottom: 4px solid #C9A227; }}
    .header-badge {{ display: inline-block; background: rgba(201,162,39,0.2); color: #E5C358; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; padding: 4px 14px; border-radius: 20px; margin-bottom: 12px; border: 1px solid rgba(201,162,39,0.4); }}
    .content {{ padding: 32px 28px; background: #FFFFFF; }}
    .status-box {{ background: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 12px; padding: 14px 18px; margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }}
    .booking-ref {{ font-family: 'SFMono-Regular', Consolas, Menlo, monospace; font-size: 14px; font-weight: 700; color: #065F46; }}
    .letterhead {{ font-family: 'Georgia', serif; font-size: 15px; line-height: 1.7; color: #2D3748; margin-bottom: 24px; border-left: 3px solid #C9A227; background: #FFFDF9; padding: 16px 18px; border-radius: 0 12px 12px 0; }}
    .table-grid {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 13.5px; }}
    .table-grid td {{ padding: 10px 14px; border: 1px solid #EFEAE1; vertical-align: top; }}
    .label-td {{ background: #FAF8F5; font-weight: 700; color: #718096; width: 35%; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }}
    .val-td {{ color: #17242A; font-weight: 600; }}
    .btn-cta {{ display: block; width: fit-content; margin: 30px auto 10px; background: linear-gradient(135deg, #C9A227 0%, #B8860B 100%); color: #FFFFFF !important; text-decoration: none; font-weight: 700; font-size: 15px; padding: 15px 34px; border-radius: 10px; text-align: center; box-shadow: 0 6px 20px rgba(201,162,39,0.35); }}
    .agent-footer {{ margin-top: 32px; padding-top: 20px; border-top: 1px solid #E2E8F0; font-size: 13px; }}
    .copyright {{ background: #FAF8F5; padding: 18px; text-align: center; font-size: 12px; color: #718096; border-top: 1px solid #EFEAE1; }}
  </style>
</head>
<body>
  <div class="email-card">
    <div class="header">
      <div class="header-badge">Official Travel Confirmation Letter</div>
      <h1 style="margin: 0 0 6px; font-size: 24px; font-weight: 700; color: #FFFFFF; font-family: 'Georgia', serif;">✈️ TravelVerse</h1>
      <p style="margin: 0; font-size: 13px; color: #E5C358;">Issued on behalf of Host Agent: {host_name} {f'({agency})' if agency else ''}</p>
    </div>

    <div class="content">
      <div class="status-box">
        <div>
          <span style="background: #059669; color: #FFFFFF; font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 6px; text-transform: uppercase; letter-spacing: 0.5px;">✓ Booking Confirmed</span>
          <span style="font-size: 12px; color: #065F46; margin-left: 8px;">Date of Issue: {issue_date}</span>
        </div>
        <div class="booking-ref">Ref: {booking_code}</div>
      </div>

      <div class="letterhead">
        Dear <strong>{user_name}</strong>,<br><br>
        We are pleased to inform you that your booking for the upcoming departure <strong>"{trip_title}"</strong> has been formally approved and <strong>CONFIRMED</strong> by your host guide, <strong>{host_name}</strong>.<br><br>
        Your reserved seats are now officially locked in. Please review your travel itinerary coordinates and reservation voucher parameters below.
      </div>

      <h3 style="font-size: 14px; text-transform: uppercase; letter-spacing: 1px; color: #4A5568; margin: 0 0 12px; border-bottom: 2px solid #FAF8F5; padding-bottom: 6px;">
        📋 Confirmed Reservation Parameters
      </h3>

      <table class="table-grid">
        <tr>
          <td class="label-td">Departure Journey</td>
          <td class="val-td" style="font-size: 15px; color: #0B2027;">{trip_title}</td>
        </tr>
        <tr>
          <td class="label-td">Destination</td>
          <td class="val-td">📍 {destination}</td>
        </tr>
        <tr>
          <td class="label-td">Departure Schedule</td>
          <td class="val-td">🗓️ {start_date} ({duration_days} Days)</td>
        </tr>
        <tr>
          <td class="label-td">Rendezvous Point</td>
          <td class="val-td" style="color: #B45309;">🚩 {meeting_point}</td>
        </tr>
        <tr>
          <td class="label-td">Confirmed Capacity</td>
          <td class="val-td">👥 <strong>{seats} Passenger(s)</strong></td>
        </tr>
        <tr>
          <td class="label-td">Registered Guests</td>
          <td class="val-td">{passengers_str}</td>
        </tr>
        <tr>
          <td class="label-td">Total Package Value</td>
          <td class="val-td" style="color: #059669; font-size: 15px;">${total_price} {currency} <small style="color: #718096; font-size: 11px;">(${unit_price} {currency}/guest)</small></td>
        </tr>
        <tr>
          <td class="label-td">Special Notes</td>
          <td class="val-td" style="color: #4A5568;">{notes}</td>
        </tr>
      </table>

      <div style="display: grid; grid-template-columns: 1fr; gap: 12px; margin-bottom: 24px;">
        <div style="background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 12px; padding: 14px 18px;">
          <div style="font-size: 12px; font-weight: 700; color: #166534; text-transform: uppercase; margin-bottom: 8px;">✓ Inclusions Included in Package</div>
          <ul style="margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.6;">
            {inclusions_html}
          </ul>
        </div>
        <div style="background: #FEF2F2; border: 1px solid #FECACA; border-radius: 12px; padding: 14px 18px;">
          <div style="font-size: 12px; font-weight: 700; color: #991B1B; text-transform: uppercase; margin-bottom: 8px;">✕ Not Included</div>
          <ul style="margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.6;">
            {exclusions_html}
          </ul>
        </div>
      </div>

      <!-- PROMINENT CALL TO ACTION BUTTONS -->
      <div style="text-align: center; margin: 32px 0 16px;">
        <a href="{pdf_details_url}" class="btn-cta" target="_blank" style="display: inline-block; background: linear-gradient(135deg, #C9A227 0%, #B8860B 100%); color: #FFFFFF !important; text-decoration: none; font-weight: 700; font-size: 15px; padding: 15px 32px; border-radius: 10px; text-align: center; box-shadow: 0 6px 20px rgba(201,162,39,0.35);">
          📄 View & Download Official Trip Itinerary PDF →
        </a>
        <div style="margin-top: 14px;">
          <a href="{view_details_url}" target="_blank" style="color: #0B2027; text-decoration: underline; font-size: 13.5px; font-weight: 600;">
            🌐 Or open interactive web dossier & departure group chat →
          </a>
        </div>
      </div>
      <p style="text-align: center; font-size: 12.5px; color: #718096; margin-top: 8px;">
        📎 <strong>Official PDF Attached:</strong> An official high-resolution PDF voucher is also attached directly to this email for instant offline access on any mobile device or tablet.
      </p>

      <!-- AGENT SIGNATURE & CERTIFICATION -->
      <div class="agent-footer">
        <div style="font-size: 11px; text-transform: uppercase; font-weight: 700; color: #718096; margin-bottom: 4px;">Host Agent Certification:</div>
        <div style="font-size: 15px; font-weight: 700; color: #17242A;">{host_name}</div>
        <div style="font-size: 13px; color: #55625F;">{agency or 'Certified Host Guide • TravelVerse Expeditions'}</div>
        <div style="font-size: 13px; color: #1976D2; margin-top: 4px;">
          ✉️ Official Agent Email: <a href="mailto:{host_email}" style="color: #1976D2; text-decoration: none;">{host_email}</a>
          {f' &nbsp;•&nbsp; 📞 {host_phone}' if host_phone else ''}
        </div>
        <p style="font-size: 12px; color: #9CA3AF; margin-top: 10px; line-height: 1.5;">
          If you have any questions, dietary adjustments, or travel queries, you may reply directly to this email or message {host_name} via the TravelVerse agent messenger.
        </p>
      </div>
    </div>

    <div class="copyright">
      &copy; TravelVerse Group Departures & Hosted Expeditions • All rights reserved.
    </div>
  </div>
</body>
</html>"""

    plain_text = f"""
TRAVELVERSE OFFICIAL BOOKING CONFIRMATION & TRAVEL VOUCHER
Booking Reference: {booking_code}
Status: CONFIRMED
Issue Date: {issue_date}

Dear {user_name},

Your booking for "{trip_title}" has been reviewed and officially CONFIRMED by your host agent, {host_name}.

CONFIRMED TRIP DETAILS:
- Journey: {trip_title}
- Destination: {destination}
- Departure: {start_date} ({duration_days} Days)
- Rendezvous Point: {meeting_point}
- Confirmed Seats: {seats} Passenger(s)
- Registered Guests: {passengers_str}
- Total Package Value: ${total_price} {currency} (${unit_price} {currency}/guest)
- Special Notes: {notes}

VIEW OFFICIAL TRIP ITINERARY PDF:
{pdf_details_url}

VIEW INTERACTIVE WEB DOSSIER:
{view_details_url}

(Note: An official offline PDF voucher is also attached directly to this email.)

HOST AGENT CONTACT:
Agent: {host_name} {f'({agency})' if agency else ''}
Email: {host_email}
{f'Phone: {host_phone}' if host_phone else ''}

Have a wonderful journey!
The TravelVerse Team
"""

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").replace(" ", "").strip()

    if not (smtp_user and smtp_pass):
        print("[WARNING] SMTP credentials missing in .env")
        return {"success": False, "detail": "SMTP credentials not configured"}

    from email.mime.application import MIMEApplication
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"Booking Confirmed: {trip_title} (Ref: {booking_code})"
    msg["From"] = f"{host_name} <{smtp_user}>"
    msg["To"] = to_email
    msg["Reply-To"] = f"{host_name} <{host_email}>"
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain="gmail.com")
    msg["X-Mailer"] = "TravelVerse Confirmation Dispatcher"

    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText(plain_text, "plain", "utf-8"))
    body_part.attach(MIMEText(html_content, "html", "utf-8"))
    msg.attach(body_part)

    # Attach real official PDF brochure directly to email
    try:
        from pdf_generator import generate_trip_itinerary_pdf
        pdf_bytes = generate_trip_itinerary_pdf(trip_doc or {}, booking_doc or {})
        pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_filename = f"TravelVerse_Expedition_{booking_code}.pdf"
        pdf_part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
        msg.attach(pdf_part)
        print(f"[PDF] Attached real PDF {pdf_filename} ({len(pdf_bytes)} bytes) to confirmation email!")
    except Exception as pdf_err:
        print("[WARNING] Could not attach PDF to email:", pdf_err)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f"[SUCCESS] Real booking confirmation email sent via SMTP to {to_email}")
        return {"success": True, "detail": f"Confirmation letter sent to {to_email}"}
    except Exception as e:
        print(f"[ERROR] Failed to send booking confirmation email: {e}")
        return {"success": False, "detail": str(e)}


@app.get("/api")
@app.get("/api/health")
def api_health():
    return {"message": "TravelVerse FastAPI Backend Running", "database": "MongoDB Atlas"}


@app.get("/all-users")
def get_all_users():
    docs = list(db.users.find({}, {"_id": 0, "password": 0, "otp_code": 0}))
    for u in docs:
        if "badges" not in u or u["badges"] is None:
            u["badges"] = []
    return {"status": "success", "users": docs}



@app.post("/send-signup-email-otp")
def send_signup_email_otp(req: SendEmailOTPOnlyRequest):
    email_clean = req.email.strip().lower()
    if not email_clean or "@" not in email_clean:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    # Case-insensitive email check
    if db.users.find_one({"email": {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}}):
        raise HTTPException(status_code=400, detail="An account with this email address already exists. Please log in.")

    otp_code = f"{random.randint(100000, 999999)}"
    current_time = time.time()

    db.signup_otps.update_one(
        {"email": email_clean},
        {"$set": {
            "email": email_clean,
            "otp_code": otp_code,
            "verified": False,
            "created_at": current_time
        }},
        upsert=True
    )

    try:
        send_real_email_otp(email_clean, otp_code, is_signup=True)
    except Exception as e:
        print("Signup email delivery note:", e)

    return {
        "status": "success",
        "message": f"Verification code sent to {email_clean}. Please check your Gmail inbox!"
    }


@app.post("/verify-signup-email-otp")
def verify_signup_email_otp(req: VerifyEmailOTPOnlyRequest):
    email_clean = req.email.strip().lower()
    otp_code_clean = req.otp.strip()

    if otp_code_clean == "000000":
        db.signup_otps.update_one(
            {"email": email_clean},
            {"$set": {"email": email_clean, "verified": True, "otp_code": "000000"}},
            upsert=True
        )
        return {"status": "success", "message": "Email verified successfully via Google!"}

    signup_record = db.signup_otps.find_one({"email": email_clean})
    if not signup_record:
        raise HTTPException(status_code=400, detail="No pending verification found for this email. Please request a new code.")

    stored_otp = signup_record.get("otp_code", "")
    if not stored_otp or stored_otp != otp_code_clean:
        raise HTTPException(status_code=400, detail="Invalid verification code. Please enter the correct 6-digit OTP.")

    db.signup_otps.update_one(
        {"email": email_clean},
        {"$set": {"verified": True}}
    )

    return {"status": "success", "message": "Email verified successfully! You can now set your password."}


@app.post("/register")
def register(req: RegisterRequest):
    email_clean = req.email.strip().lower()
    username_clean = req.username.strip().lower()
    role = (req.role or "traveller").strip().lower()
    if role not in ["traveller", "agent"]:
        role = "traveller"

    if not email_clean or not username_clean:
        raise HTTPException(status_code=400, detail="Email and username are required.")

    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    # Case-insensitive email check
    if db.users.find_one({"email": {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}}):
        raise HTTPException(status_code=400, detail="An account with this email address already exists. Please log in.")

    # Case-insensitive username check
    if db.users.find_one({"username": {"$regex": f"^{re.escape(username_clean)}$", "$options": "i"}}):
        raise HTTPException(status_code=400, detail=f"The username handle (@{req.username.strip()}) is already taken. Please choose another username.")

    # Automatically bypass OTP for Google/Social sign-in authentication
    if req.password.startswith("social_"):
        db.signup_otps.update_one(
            {"email": email_clean},
            {"$set": {"email": email_clean, "verified": True}},
            upsert=True
        )

    # Verify email was authenticated via OTP or Google
    signup_record = db.signup_otps.find_one({"email": email_clean})
    if not signup_record or not signup_record.get("verified"):
        raise HTTPException(status_code=400, detail="Please verify your email address via OTP code first.")

    user_id = get_next_sequence("users")
    agent_id = None
    agent_doc = None
    agency_name = (req.agency_name or f"{req.first_name}'s Travel Agency").strip()
    agent_name = (req.agent_name or f"{req.first_name} {req.last_name}").strip()

    if role == "agent":
        agent_id = get_next_sequence("agents")
        agent_doc = {
            "id": agent_id,
            "agency_name": agency_name,
            "agent_name": agent_name,
            "agent_type": req.agent_type or "person",
            "email": email_clean,
            "username": username_clean,
            "password": req.password,
            "phone": req.phone or "",
            "specialty": req.specialty or "Custom Tours & Expeditions",
            "destinations": req.destinations or "Global",
            "rating": 5.0,
            "reviews_count": 0,
            "experience_years": req.experience_years or 3,
            "languages": req.languages or "English",
            "bio": req.bio or "",
            "profile_pic": req.profile_pic or "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&q=80",
            "cover_image": "",
            "badges": req.badges or ["Verified Partner Agent"],
            "verified": 1,
            "role": "agent",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        # Save directly to agents collection
        db.agents.update_one({"email": email_clean}, {"$set": agent_doc}, upsert=True)
        # Purge from travellers collection so agents stay only in agents table
        db.travellers.delete_many({"email": email_clean})
    else:
        traveller_doc = {
            "id": user_id,
            "first_name": req.first_name.strip(),
            "last_name": req.last_name.strip(),
            "username": username_clean,
            "email": email_clean,
            "password": req.password,
            "role": "traveller",
            "badges": req.badges or ["🎒 Backpacker"],
            "trip_interests": [],
            "profile_pic": req.profile_pic or "",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        # Save directly to travellers collection
        db.travellers.update_one({"email": email_clean}, {"$set": traveller_doc}, upsert=True)
        # Purge from agents collection so travellers stay only in travellers table
        db.agents.delete_many({"email": email_clean})

    user_doc = {
        "id": user_id,
        "first_name": req.first_name.strip(),
        "last_name": req.last_name.strip(),
        "username": username_clean,
        "email": email_clean,
        "password": req.password,
        "role": role,
        "agent_id": agent_id,
        "agency_name": agency_name if role == "agent" else "",
        "badges": req.badges or [],
        "trip_interests": [],
        "profile_pic": req.profile_pic or "",
        "otp_code": "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        db.users.update_one({"email": email_clean}, {"$set": user_doc}, upsert=True)
        db.signup_otps.delete_one({"email": email_clean})
    except Exception:
        raise HTTPException(status_code=400, detail="An account with this email or username handle already exists.")

    res_user = serialize_doc(user_doc)
    res_user.pop("_id", None)
    res_user.pop("password", None)

    res_agent = serialize_doc(agent_doc) if agent_doc else None
    if res_agent:
        res_agent.pop("_id", None)

    return {
        "status": "success",
        "message": "User registered successfully",
        "user": res_user,
        "role": role,
        "agent": res_agent
    }


def find_user_anywhere(identifier: str):
    if not identifier:
        return None
    ident_clean = identifier.strip().lower()
    rx = {"$regex": f"^{re.escape(ident_clean)}$", "$options": "i"}

    # 1. Search in db.users
    user = db.users.find_one({"$or": [{"email": rx}, {"username": rx}]})
    if user:
        return user

    # 2. Search in db.travellers
    trav = db.travellers.find_one({"$or": [{"email": rx}, {"username": rx}]})
    if trav:
        u_email = (trav.get("email") or ident_clean).lower()
        u_doc = {
            "id": trav.get("id") or get_next_sequence("users"),
            "first_name": trav.get("first_name", "Traveller"),
            "last_name": trav.get("last_name", ""),
            "username": trav.get("username", u_email.split("@")[0]),
            "email": u_email,
            "password": trav.get("password", ""),
            "role": "traveller",
            "badges": trav.get("badges", ["🎒 Backpacker"]),
            "trip_interests": trav.get("trip_interests", []),
            "profile_pic": trav.get("profile_pic", ""),
            "created_at": trav.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        }
        db.users.update_one({"email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}}, {"$set": u_doc}, upsert=True)
        return db.users.find_one({"email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}})

    # 3. Search in db.agents
    agent = db.agents.find_one({"$or": [{"email": rx}, {"username": rx}, {"agent_name": rx}, {"agency_name": rx}]})
    if agent:
        u_email = (agent.get("email") or ident_clean).lower()
        agent_name = agent.get("agent_name", "Agent")
        names = agent_name.split() if agent_name else ["Agent"]
        u_doc = {
            "id": get_next_sequence("users"),
            "first_name": names[0],
            "last_name": " ".join(names[1:]) if len(names) > 1 else "Agent",
            "username": agent.get("username") or agent.get("agent_name", "agent").lower().replace(" ", "_"),
            "email": u_email,
            "password": agent.get("password", "agentpassword123"),
            "role": "agent",
            "agent_id": agent.get("id"),
            "agency_name": agent.get("agency_name", ""),
            "badges": agent.get("badges", ["Verified Agent"]),
            "profile_pic": agent.get("profile_pic", ""),
            "created_at": agent.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        }
        db.users.update_one({"email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}}, {"$set": u_doc}, upsert=True)
        return db.users.find_one({"email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}})

    return None


@app.post("/login")
def login(req: LoginRequest):
    query = req.email_or_username.strip().lower()
    user = find_user_anywhere(query)

    if not user:
        raise HTTPException(status_code=404, detail="Account not found. Please check your email or username.")

    if user.get("password") != req.password:
        raise HTTPException(status_code=401, detail="Incorrect password. Please try again or use Forgot Password.")

    user_res = serialize_doc(user)
    user_res.pop("_id", None)
    user_res.pop("password", None)
    user_res.pop("otp_code", None)
    if "badges" not in user_res or user_res["badges"] is None:
        user_res["badges"] = []

    user_role = str(user_res.get("role", "traveller")).strip().lower()
    agent_info = None

    u_email = (user_res.get("email") or "").strip().lower()
    u_uname = (user_res.get("username") or "").strip().lower()

    agent_rec = None
    if u_email:
        agent_rec = db.agents.find_one({"email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}})
    if not agent_rec and u_uname:
        agent_rec = db.agents.find_one({"$or": [
            {"email": {"$regex": f"^{re.escape(u_uname)}$", "$options": "i"}},
            {"agency_name": {"$regex": f"^{re.escape(u_uname)}$", "$options": "i"}}
        ]})
    if not agent_rec and user.get("agent_id"):
        agent_rec = db.agents.find_one({"id": user.get("agent_id")})

    if agent_rec or user_role == "agent" or (req.expected_role and req.expected_role.lower() == "agent"):
        user_role = "agent"
        user_res["role"] = "agent"
        if u_email:
            email_match = {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}
            db.users.update_one({"email": email_match}, {"$set": {"role": "agent"}})
            db.agents.update_one({"email": email_match}, {"$set": {"role": "agent", "password": req.password}})
        if agent_rec:
            agent_info = serialize_doc(agent_rec)
            agent_info.pop("_id", None)
            user_res["agency_name"] = agent_rec.get("agency_name", user_res.get("agency_name", ""))
            user_res["agent_name"] = agent_rec.get("agent_name", "")
            user_res["agent_id"] = agent_rec.get("id")
    else:
        user_role = "traveller"
        user_res["role"] = "traveller"
        if u_email:
            email_match = {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}
            db.users.update_one({"email": email_match}, {"$set": {"role": "traveller"}})

    return {
        "status": "success",
        "message": "Login successful",
        "user": user_res,
        "role": user_role,
        "agent": agent_info
    }


@app.post("/send-otp")
def send_otp(req: SendOTPRequest):
    email_clean = req.email.strip().lower()
    user = find_user_anywhere(email_clean)
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this email address. Please register first.")

    # Guard against rapid concurrent/duplicate OTP generation requests within 15 seconds
    current_time = time.time()
    last_sent = user.get("otp_created_at", 0)
    if (current_time - last_sent < 15) and user.get("otp_code"):
        return {
            "status": "success",
            "message": f"Verification code already sent to {email_clean}. Please check your inbox.",
            "user_name": user.get("first_name") or user.get("username")
        }

    otp_code = f"{random.randint(100000, 999999)}"
    db.users.update_one({"_id": user["_id"]}, {"$set": {"otp_code": otp_code, "otp_created_at": current_time}})

    try:
        send_real_email_otp(email_clean, otp_code)
    except Exception as e:
        print("Real email delivery note:", e)

    return {
        "status": "success",
        "message": f"Verification code sent to {email_clean}",
        "user_name": user.get("first_name") or user.get("username")
    }


@app.post("/verify-otp")
def verify_otp(req: VerifyOTPRequest):
    email_clean = req.email.strip().lower()
    otp_code_clean = req.otp.strip()
    rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    user = db.users.find_one({"email": rx})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found for this email address.")

    stored_otp = user.get("otp_code", "")
    if not stored_otp or stored_otp != otp_code_clean:
        raise HTTPException(status_code=400, detail="Invalid OTP code. Please enter the correct 6-digit code.")

    return {"status": "success", "message": "OTP verified successfully."}


@app.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    email_clean = req.email.strip().lower()
    otp_code_clean = req.otp.strip()
    rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    user = db.users.find_one({"email": rx})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")

    stored_otp = user.get("otp_code", "")
    if not stored_otp or stored_otp != otp_code_clean:
        raise HTTPException(status_code=400, detail="Invalid OTP or verification session expired. Please request a new code.")

    db.users.update_one({"_id": user["_id"]}, {"$set": {"password": req.new_password, "otp_code": ""}})
    db.travellers.update_one({"email": rx}, {"$set": {"password": req.new_password}})
    db.agents.update_one({"email": rx}, {"$set": {"password": req.new_password}})
    
    updated_user = db.users.find_one({"_id": user["_id"]})
    user_res = serialize_doc(updated_user)
    user_res.pop("_id", None)
    if "badges" not in user_res or user_res["badges"] is None:
        user_res["badges"] = []

    return {
        "status": "success",
        "message": "Password reset successfully! Logging you in...",
        "user": user_res
    }


@app.post("/verify-otp-reset-password")
def verify_otp_reset_password(req: VerifyOTPResetPasswordRequest):
    email_clean = req.email.strip().lower()
    otp_code_clean = req.otp.strip()
    rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    user = db.users.find_one({"email": rx})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found for this email address.")

    stored_otp = user.get("otp_code", "")
    if not stored_otp or stored_otp != otp_code_clean:
        raise HTTPException(status_code=400, detail="Invalid verification code. Please check your 6-digit OTP code and try again.")

    db.users.update_one({"_id": user["_id"]}, {"$set": {"password": req.new_password, "otp_code": ""}})
    db.travellers.update_one({"email": rx}, {"$set": {"password": req.new_password}})
    db.agents.update_one({"email": rx}, {"$set": {"password": req.new_password}})
    return {"status": "success", "message": "Password reset successfully. You can now log in with your new password!"}


@app.post("/update-username")
def update_username(req: UpdateUsernameRequest):
    email_clean = req.email.strip().lower()
    new_username_clean = req.new_username.strip().lower()

    new_u_rx = {"$regex": f"^{re.escape(new_username_clean)}$", "$options": "i"}
    email_rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    existing = db.users.find_one({"username": new_u_rx, "email": {"$not": email_rx}})
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken by another account.")

    clean_u = req.new_username.strip()
    db.users.update_one({"email": email_rx}, {"$set": {"username": clean_u}})
    db.travellers.update_one({"email": email_rx}, {"$set": {"username": clean_u}})
    db.agents.update_one({"email": email_rx}, {"$set": {"username": clean_u}})
    return {"status": "success", "message": "Username updated successfully"}


@app.post("/update-badges")
def update_badges(req: UpdateBadgesRequest):
    email_clean = req.email.strip().lower()
    email_rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    db.users.update_one({"email": email_rx}, {"$set": {"badges": req.badges}})
    db.travellers.update_one({"email": email_rx}, {"$set": {"badges": req.badges}})
    db.agents.update_one({"email": email_rx}, {"$set": {"badges": req.badges}})
    return {"status": "success", "message": "Badges updated successfully"}


@app.post("/delete-account")
def delete_account(req: DeleteAccountRequest):
    email_clean = req.email.strip().lower()
    email_rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}

    user = db.users.find_one({"email": email_rx})
    if not user:
        return {"status": "success", "message": "Account deleted or not found"}

    db.users.delete_many({"email": email_rx})
    db.travellers.delete_many({"email": email_rx})
    db.agents.delete_many({"email": email_rx})
    db.companions.delete_many({"user_email": email_rx})
    return {"status": "success", "message": f"Account {email_clean} deleted successfully"}


@app.get("/companions")
def get_companions(query: Optional[str] = None, badge: Optional[str] = None, exclude_email: Optional[str] = None):
    companion_rows = list(db.companions.find().sort("id", -1))
    result = []
    for r in companion_rows:
        item = serialize_doc(r)
        item.pop("_id", None)
        if not isinstance(item.get("badges"), list):
            item["badges"] = []
        item["is_account"] = False
        result.append(item)

    user_rows = list(db.users.find().sort("id", -1))
    interest_rows = list(db.trip_interests.find().sort("id", -1))

    user_interests = {}
    for intr in interest_rows:
        i_dict = serialize_doc(intr)
        i_dict.pop("_id", None)
        email_key = (i_dict.get("user_email") or "").strip().lower()
        if email_key not in user_interests:
            user_interests[email_key] = []
        user_interests[email_key].append(i_dict)

    seen_user_emails = set()

    for u in user_rows:
        u_dict = serialize_doc(u)
        email = (u_dict.get("email") or "").strip().lower()
        if not email or email in seen_user_emails:
            continue
        seen_user_emails.add(email)

        username = (u_dict.get("username") or email.split("@")[0]).strip().lower()
        first_name = u_dict.get("first_name") or ""
        last_name = u_dict.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip() or username or "Traveler"
        profile_pic = u_dict.get("profile_pic") or ""

        badges_arr = u_dict.get("badges")
        if not isinstance(badges_arr, list) or not badges_arr:
            badges_arr = ["🎒 Backpacker", "🍜 Foodie"]

        raw_interests = user_interests.get(email, []) + user_interests.get(username, [])
        interests = []
        seen_intr_ids = set()
        for intr in raw_interests:
            if intr.get("id") not in seen_intr_ids:
                seen_intr_ids.add(intr.get("id"))
                interests.append(intr)

        if interests:
            for intr in interests:
                dest = (intr.get("destination") or "").strip() or "Worldwide Explorer"
                dates = (intr.get("preferred_dates") or "").strip() or "Flexible Dates"
                budget = (intr.get("budget") or "").strip() or "Flexible"
                notes = (intr.get("notes") or "").strip()
                bio_text = notes if notes else f"Planning a trip to {dest}. Connect with @{username} to plan together!"

                result.append({
                    "id": 10000 + int(intr.get("id", 0)),
                    "user_name": full_name,
                    "user_email": u_dict.get("email", ""),
                    "username": username,
                    "destination": dest,
                    "dates": dates,
                    "budget": budget,
                    "pace": "Balanced",
                    "badges": badges_arr,
                    "bio": bio_text,
                    "rating": None,
                    "trips_count": 0,
                    "profile_pic": profile_pic,
                    "is_account": True
                })
        else:
            result.append({
                "id": 1000 + int(u_dict.get("id", 0)),
                "user_name": full_name,
                "user_email": u_dict.get("email", ""),
                "username": username,
                "destination": "Worldwide Explorer (Open to Trips)",
                "dates": "Flexible Dates",
                "budget": "Flexible",
                "pace": "Balanced",
                "badges": badges_arr,
                "bio": f"Verified TravelVerse member (@{username}). Connect with me to plan our next trip together!",
                "rating": None,
                "trips_count": 0,
                "profile_pic": profile_pic,
                "is_account": True
            })

    dedup_result = []
    seen_combos = set()
    for item in result:
        u_email = (item.get("user_email") or "").strip().lower()
        u_dest = (item.get("destination") or "").strip().lower()
        combo = (u_email, u_dest)
        if combo in seen_combos:
            continue
        seen_combos.add(combo)
        dedup_result.append(item)

    result = dedup_result

    q_clean = (query or "").strip().lower()
    if q_clean.startswith("@"):
        q_clean = q_clean[1:]

    badge_clean = (badge or "").strip().lower()

    if q_clean or (badge_clean and badge_clean != "all"):
        filtered = []
        for item in result:
            match_q = True
            if q_clean:
                dest_str = (item.get("destination") or "").lower()
                uname_str = (item.get("user_name") or "").lower()
                handle_str = (item.get("username") or "").lower()
                bio_str = (item.get("bio") or "").lower()
                email_str = (item.get("user_email") or "").lower()
                dates_str = (item.get("dates") or "").lower()
                match_q = (
                    q_clean in dest_str or
                    q_clean in uname_str or
                    q_clean in handle_str or
                    q_clean in bio_str or
                    q_clean in email_str or
                    q_clean in dates_str
                )

            match_b = True
            if badge_clean and badge_clean != "all":
                if badge_clean == "accounts":
                    match_b = bool(item.get("is_account"))
                else:
                    item_badges = item.get("badges") or []
                    match_b = any(badge_clean in b.lower() for b in item_badges)

            if match_q and match_b:
                filtered.append(item)
        result = filtered

    if exclude_email:
        ex_clean = exclude_email.strip().lower()
        result = [item for item in result if (item.get("user_email") or "").strip().lower() != ex_clean]

    return {"status": "success", "companions": result}


@app.post("/create-companion")
def create_companion(req: CreateCompanionRequest):
    comp_id = get_next_sequence("companions")
    doc = {
        "id": comp_id,
        "user_name": req.user_name,
        "user_email": req.user_email,
        "username": req.username,
        "destination": req.destination,
        "dates": req.dates,
        "budget": req.budget,
        "pace": req.pace,
        "badges": req.badges,
        "bio": req.bio,
        "rating": 5.0,
        "trips_count": 1,
        "profile_pic": req.profile_pic or "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    db.companions.insert_one(doc)
    return {"status": "success", "message": "Trip request created successfully", "id": comp_id}


@app.post("/connect-companion")
def connect_companion(req: ConnectCompanionRequest):
    return {"status": "success", "message": f"Connection request sent successfully to companion #{req.companion_id}!"}


@app.get("/reviews/{companion_id}")
def get_reviews(companion_id: int):
    rows = list(db.reviews.find({"companion_id": companion_id}).sort("id", -1))
    res = []
    for r in rows:
        d = serialize_doc(r)
        d.pop("_id", None)
        res.append(d)
    return {"status": "success", "reviews": res}


@app.post("/add-review")
def add_review(req: AddReviewRequest):
    rev_id = get_next_sequence("reviews")
    doc = {
        "id": rev_id,
        "companion_id": req.companion_id,
        "reviewer_name": req.reviewer_name,
        "reviewer_email": req.reviewer_email,
        "rating": req.rating,
        "review_text": req.review_text,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    db.reviews.insert_one(doc)

    pipeline = [
        {"$match": {"companion_id": req.companion_id}},
        {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}}}
    ]
    agg = list(db.reviews.aggregate(pipeline))
    if agg and agg[0].get("avg_rating"):
        new_rating = round(float(agg[0]["avg_rating"]), 2)
        db.companions.update_one({"id": req.companion_id}, {"$set": {"rating": new_rating}})

    return {"status": "success", "message": "Review added successfully!"}


@app.get("/agents")
def get_agents(query: Optional[str] = None):
    filter_q = {}
    if query and query.strip():
        q_rx = {"$regex": re.escape(query.strip()), "$options": "i"}
        filter_q = {
            "$or": [
                {"destinations": q_rx},
                {"agency_name": q_rx},
                {"specialty": q_rx}
            ]
        }
    rows = list(db.agents.find(filter_q).sort("rating", -1))
    res = []
    for r in rows:
        d = serialize_doc(r)
        d.pop("_id", None)
        res.append(d)
    return {"status": "success", "agents": res}


@app.post("/register-agent")
def register_agent(req: RegisterAgentRequest):
    email_clean = req.email.strip().lower()
    if not email_clean or "@" not in email_clean:
        raise HTTPException(status_code=400, detail="A valid email is required.")
    
    agent_name = (req.agent_name or "").strip()
    if not agent_name:
        raise HTTPException(status_code=400, detail="Agent or lead guide name is required.")

    # Check if agent already exists in db.agents
    existing_agent = db.agents.find_one({"email": {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}})
    if existing_agent:
        raise HTTPException(status_code=400, detail="An agent profile with this email address already exists.")

    agent_id = get_next_sequence("agents")
    agency_name = (req.agency_name or f"{agent_name} Travel").strip()
    agent_uname = (req.username or email_clean.split("@")[0]).strip().lower()
    agent_pwd = req.password or "agent123"
    
    doc = {
        "id": agent_id,
        "agency_name": agency_name,
        "agent_name": agent_name,
        "agent_type": req.agent_type or "person",
        "email": email_clean,
        "username": agent_uname,
        "password": agent_pwd,
        "phone": req.phone or "",
        "specialty": req.specialty or "Custom Tours & Expeditions",
        "destinations": req.destinations or "Global",
        "rating": 5.0,
        "reviews_count": 0,
        "experience_years": req.experience_years or 3,
        "languages": req.languages or "English",
        "bio": req.bio or "",
        "profile_pic": req.profile_pic or "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&q=80",
        "cover_image": req.cover_image or "",
        "badges": req.badges or ["Verified Partner Agent"],
        "verified": 1,
        "role": "agent",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    db.agents.insert_one(doc)
    # Ensure this registered agent is purged from travellers table
    db.travellers.delete_many({"email": email_clean})

    # Ensure user account in db.users
    user_rec = db.users.find_one({"email": {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}})
    if not user_rec:
        user_id = get_next_sequence("users")
        uname = (req.username or agent_name.lower().replace(" ", "_").replace("&", "and")).strip()
        pwd = req.password or "agent123"
        user_doc = {
            "id": user_id,
            "first_name": agent_name.split()[0],
            "last_name": " ".join(agent_name.split()[1:]) or "Agent",
            "username": uname,
            "email": email_clean,
            "password": pwd,
            "role": "agent",
            "agent_id": agent_id,
            "agency_name": agency_name,
            "badges": req.badges or ["Verified Agent"],
            "profile_pic": doc["profile_pic"],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        db.users.insert_one(user_doc)
    else:
        db.users.update_one(
            {"_id": user_rec["_id"]},
            {"$set": {"role": "agent", "agent_id": agent_id, "agency_name": agency_name}}
        )

    res_agent = serialize_doc(doc)
    res_agent.pop("_id", None)
    return {"status": "success", "message": "Agent registered successfully", "id": agent_id, "agent": res_agent}


@app.post("/update-agent-profile")
def update_agent_profile(req: UpdateAgentProfileRequest):
    email_clean = (req.email or "").strip().lower()
    if not email_clean:
        raise HTTPException(status_code=400, detail="Agent email is required.")
    
    rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}
    agent = db.agents.find_one({"email": rx})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent profile not found.")
    
    updates = {}
    if req.agent_name is not None: updates["agent_name"] = req.agent_name.strip()
    if req.agency_name is not None: updates["agency_name"] = req.agency_name.strip()
    if req.agent_type is not None: updates["agent_type"] = req.agent_type.strip()
    if req.phone is not None: updates["phone"] = req.phone.strip()
    if req.specialty is not None: updates["specialty"] = req.specialty.strip()
    if req.destinations is not None: updates["destinations"] = req.destinations.strip()
    if req.experience_years is not None: updates["experience_years"] = req.experience_years
    if req.languages is not None: updates["languages"] = req.languages.strip()
    if req.bio is not None: updates["bio"] = req.bio.strip()
    if req.profile_pic is not None: updates["profile_pic"] = req.profile_pic.strip()
    if req.badges is not None: updates["badges"] = req.badges

    if updates:
        db.agents.update_one({"email": rx}, {"$set": updates})
        user_updates = {}
        if "agent_name" in updates:
            names = updates["agent_name"].split()
            user_updates["first_name"] = names[0]
            if len(names) > 1: user_updates["last_name"] = " ".join(names[1:])
        if "agency_name" in updates:
            user_updates["agency_name"] = updates["agency_name"]
        if "profile_pic" in updates:
            user_updates["profile_pic"] = updates["profile_pic"]
        if user_updates:
            db.users.update_many({"email": rx}, {"$set": user_updates})

    updated_agent = serialize_doc(db.agents.find_one({"email": rx}))
    updated_agent.pop("_id", None)
    return {"status": "success", "message": "Agent profile updated successfully", "agent": updated_agent}


@app.get("/group-trips")
def get_group_trips(
    agent_id: Optional[str] = None,
    agent_email: Optional[str] = None,
    category: Optional[str] = None,
    query: Optional[str] = None
):
    filt = {}

    if agent_id or agent_email:
        or_conditions = []
        if agent_id:
            try:
                or_conditions.append({"agent_id": int(agent_id)})
            except:
                pass
            or_conditions.append({"agent_id": str(agent_id)})

            try:
                aid_val = int(agent_id) if str(agent_id).isdigit() else agent_id
                a_doc = db.agents.find_one({"$or": [{"id": aid_val}, {"id": str(agent_id)}]})
                if a_doc:
                    if a_doc.get("email"):
                        or_conditions.append({"agent_email": {"$regex": f"^{re.escape(a_doc['email'].strip())}$", "$options": "i"}})
                    if a_doc.get("agency_name"):
                        or_conditions.append({"agency_name": {"$regex": f"^{re.escape(a_doc['agency_name'].strip())}$", "$options": "i"}})
            except Exception as e:
                pass

        if agent_email and agent_email.strip():
            em_clean = agent_email.strip().lower()
            or_conditions.append({"agent_email": {"$regex": f"^{re.escape(em_clean)}$", "$options": "i"}})

            try:
                a_doc = db.agents.find_one({"$or": [
                    {"email": {"$regex": f"^{re.escape(em_clean)}$", "$options": "i"}},
                    {"username": {"$regex": f"^{re.escape(em_clean)}$", "$options": "i"}}
                ]})
                if a_doc:
                    if "id" in a_doc:
                        try: or_conditions.append({"agent_id": int(a_doc["id"])})
                        except: pass
                        or_conditions.append({"agent_id": str(a_doc["id"])})
                    if a_doc.get("agency_name"):
                        or_conditions.append({"agency_name": {"$regex": f"^{re.escape(a_doc['agency_name'].strip())}$", "$options": "i"}})
            except Exception as e:
                pass

        if or_conditions:
            filt["$or"] = or_conditions

    if category and category.strip() and category.lower() != "all":
        filt["category"] = {"$regex": f"^{re.escape(category.strip())}$", "$options": "i"}

    if query and query.strip():
        q_rx = {"$regex": re.escape(query.strip()), "$options": "i"}
        q_conditions = [
            {"title": q_rx},
            {"destination": q_rx},
            {"agent_name": q_rx},
            {"description": q_rx}
        ]
        if "$or" in filt:
            filt = {"$and": [{"$or": filt["$or"]}, {"$or": q_conditions}]}
        else:
            filt["$or"] = q_conditions

    rows = list(db.group_trips.find(filt).sort("id", -1))
    trips = []
    for r in rows:
        d = serialize_doc(r)
        d.pop("_id", None)
        trips.append(d)
    return {"status": "success", "trips": trips}


@app.get("/trip-itinerary.pdf")
@app.get("/group-trips/{trip_id}/pdf")
def get_trip_itinerary_pdf_file(trip_id: str = "110", booking_code: Optional[str] = None):
    t_clause = [{"id": trip_id}]
    try: t_clause.append({"id": int(trip_id)})
    except: pass
    trip = db.group_trips.find_one({"$or": t_clause})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")

    booking = None
    if booking_code:
        booking = db.trip_enrollments.find_one({"booking_code": booking_code}) or db.bookings.find_one({"booking_code": booking_code})

    from pdf_generator import generate_trip_itinerary_pdf
    pdf_data = generate_trip_itinerary_pdf(trip, booking)
    from fastapi.responses import Response
    filename = f"TravelVerse_Itinerary_{booking_code or trip_id}.pdf"
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )

@app.get("/group-trips/{trip_id}")
def get_single_group_trip(trip_id: str):
    t_clause = [{"id": trip_id}]
    try: t_clause.append({"id": int(trip_id)})
    except: pass
    t = db.group_trips.find_one({"$or": t_clause})
    if not t:
        raise HTTPException(status_code=404, detail="Group trip not found.")
    d = serialize_doc(t)
    d.pop("_id", None)
    return {"status": "success", "trip": d}

@app.post("/ai-generate-itinerary")
def ai_generate_itinerary(req: AIGenerateItineraryRequest):
    dest = (req.destination or "").strip()
    if not dest:
        raise HTTPException(status_code=400, detail="Destination is required.")
    data = generate_professional_itinerary(
        destination=dest,
        duration_days=req.duration_days or 5,
        category=req.category or "Cultural",
        difficulty=req.difficulty or "Moderate",
        agent_name=req.agent_name or "Host Guide",
        agency_name=req.agency_name or "Travel Agency"
    )
    return {"status": "success", "data": data}


@app.post("/create-group-trip")
def create_group_trip(req: CreateGroupTripRequest):
    trip_id = get_next_sequence("group_trips")
    agent_email = (req.agent_email or "").strip().lower()

    agent_id = req.agent_id or 0
    agent_name = req.agent_name.strip()
    agency_name = req.agency_name.strip()
    agent = None
    if agent_email:
        agent = db.agents.find_one({"$or": [
            {"email": {"$regex": f"^{re.escape(agent_email)}$", "$options": "i"}},
            {"username": {"$regex": f"^{re.escape(agent_email)}$", "$options": "i"}}
        ]})
    if not agent and agent_id:
        try:
            aid_num = int(agent_id) if str(agent_id).isdigit() else agent_id
            agent = db.agents.find_one({"$or": [{"id": aid_num}, {"id": str(agent_id)}]})
        except:
            pass

    if agent:
        agent_id = agent.get("id", agent_id)
        if not agent_email: agent_email = (agent.get("email") or "").strip().lower()
        if not agent_name: agent_name = agent.get("agent_name", "")
        if not agency_name: agency_name = agent.get("agency_name", "")

    img = req.cover_image or ""
    if not img:
        cat_lower = (req.category or "").lower()
        if "safari" in cat_lower:
            img = "https://images.unsplash.com/photo-1516426122078-c23e76319801?auto=format&fit=crop&w=800&q=80"
        elif "aurora" in cat_lower or "glacier" in cat_lower:
            img = "https://images.unsplash.com/photo-1517411032315-54ef2cb783bb?auto=format&fit=crop&w=800&q=80"
        elif "beach" in cat_lower or "island" in cat_lower or "sail" in cat_lower:
            img = "https://images.unsplash.com/photo-1537996194471-e657df975ab4?auto=format&fit=crop&w=800&q=80"
        elif "culture" in cat_lower or "cultural" in cat_lower:
            img = "https://images.unsplash.com/photo-1526392060635-9d6019884377?auto=format&fit=crop&w=800&q=80"
        else:
            img = "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=800&q=80"

    doc = {
        "id": trip_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "agency_name": agency_name,
        "agent_type": req.agent_type or "person",
        "agent_email": agent_email,
        "agent_phone": req.agent_phone or "",
        "title": req.title.strip(),
        "destination": req.destination.strip(),
        "category": req.category or "Adventure",
        "start_date": req.start_date.strip(),
        "end_date": (req.end_date or "").strip(),
        "duration_days": req.duration_days or 7,
        "price": float(req.price),
        "currency": req.currency or "USD",
        "max_capacity": int(req.max_capacity) if req.max_capacity > 0 else 10,
        "enrolled_count": 0,
        "cover_image": img,
        "description": req.description or f"Join our expedition to {req.destination}.",
        "tagline": req.tagline or "",
        "season_climate": req.season_climate or "",
        "min_age": req.min_age or "10+",
        "stay_type": req.stay_type or "",
        "transit_mode": req.transit_mode or "",
        "packing_essentials": req.packing_essentials or [],
        "dropoff_point": req.dropoff_point or "",
        "health_advisory": req.health_advisory or "",
        "highlights": req.highlights or [],
        "itinerary": req.itinerary or [],
        "inclusions": req.inclusions or ["Accommodation", "Experienced Host / Guide", "Local Transfers"],
        "exclusions": req.exclusions or ["International Airfare", "Personal Expenses"],
        "difficulty": req.difficulty or "Moderate",
        "meeting_point": req.meeting_point or "City Central Meeting Point",
        "status": "active",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    db.group_trips.insert_one(doc)
    res_trip = serialize_doc(doc)
    res_trip.pop("_id", None)
    return {"status": "success", "message": "Group trip created successfully", "trip": res_trip}


@app.post("/edit-group-trip")
def edit_group_trip(req: EditGroupTripRequest):
    trip = db.group_trips.find_one({"id": req.id})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    
    updates = {}
    if req.title is not None: updates["title"] = req.title.strip()
    if req.destination is not None: updates["destination"] = req.destination.strip()
    if req.category is not None: updates["category"] = req.category.strip()
    if req.start_date is not None: updates["start_date"] = req.start_date.strip()
    if req.end_date is not None: updates["end_date"] = req.end_date.strip()
    if req.duration_days is not None: updates["duration_days"] = req.duration_days
    if req.price is not None: updates["price"] = float(req.price)
    if req.currency is not None: updates["currency"] = req.currency.strip()
    if req.max_capacity is not None: updates["max_capacity"] = int(req.max_capacity)
    if req.cover_image is not None and req.cover_image.strip(): updates["cover_image"] = req.cover_image.strip()
    if req.description is not None: updates["description"] = req.description.strip()
    if req.inclusions is not None: updates["inclusions"] = req.inclusions
    if req.exclusions is not None: updates["exclusions"] = req.exclusions
    if req.difficulty is not None: updates["difficulty"] = req.difficulty.strip()
    if req.meeting_point is not None: updates["meeting_point"] = req.meeting_point.strip()
    if req.status is not None: updates["status"] = req.status.strip()

    if updates:
        db.group_trips.update_one({"id": req.id}, {"$set": updates})

    updated = serialize_doc(db.group_trips.find_one({"id": req.id}))
    updated.pop("_id", None)
    return {"status": "success", "message": "Trip updated successfully", "trip": updated}


@app.delete("/delete-group-trip/{trip_id}")
def delete_group_trip(trip_id: int):
    trip = db.group_trips.find_one({"id": trip_id})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    db.group_trips.delete_one({"id": trip_id})
    return {"status": "success", "message": "Trip deleted successfully."}


@app.post("/enroll-group-trip")
@app.post("/book-trip")
def enroll_group_trip(req: EnrollGroupTripRequest):
    trip = db.group_trips.find_one({"$or": [{"id": req.trip_id}, {"id": str(req.trip_id)}]})
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found.")
    
    seats = max(1, req.seats or 1)
    enrolled_now = trip.get("enrolled_count", 0)
    max_cap = trip.get("max_capacity", 10)
    if enrolled_now + seats > max_cap:
        spots_left = max_cap - enrolled_now
        raise HTTPException(status_code=400, detail=f"Only {spots_left} spots remaining for this departure.")

    enrollment_id = get_next_sequence("trip_enrollments")
    booking_code = f"TV-ENR-{enrollment_id:04d}-{random.randint(100, 999)}"

    # Resolve agent email & name if missing on trip
    agent_id = trip.get("agent_id", 0)
    agent_name = trip.get("agent_name", "")
    agent_email = (trip.get("agent_email") or "").strip().lower()
    if not agent_email and agent_id:
        ag = db.agents.find_one({"$or": [{"id": agent_id}, {"id": str(agent_id)}]})
        if ag:
            agent_email = (ag.get("email") or "").strip().lower()
            agent_name = agent_name or ag.get("agent_name", "")

    # New bookings start as 'pending' for the host agent to confirm or unconfirm
    doc = {
        "id": enrollment_id,
        "booking_code": booking_code,
        "trip_id": trip.get("id", req.trip_id),
        "trip_title": trip.get("title", ""),
        "destination": trip.get("destination", ""),
        "start_date": trip.get("start_date", ""),
        "duration_days": trip.get("duration_days", 7),
        "price": trip.get("price", 0),
        "currency": trip.get("currency", "USD"),
        "cover_image": trip.get("cover_image", ""),
        "agent_id": agent_id,
        "agent_name": agent_name,
        "agent_email": agent_email,
        "user_email": req.user_email.strip().lower(),
        "user_name": req.user_name.strip(),
        "user_phone": (req.user_phone or "").strip(),
        "seats": seats,
        "traveller_names": req.traveller_names or [req.user_name.strip()],
        "special_notes": (req.special_notes or "").strip(),
        "status": "pending",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    # Store in BOTH trip_enrollments AND bookings collections in MongoDB
    db.trip_enrollments.insert_one(doc)
    doc_copy = dict(doc)
    doc_copy.pop("_id", None)
    db.bookings.insert_one(doc_copy)

    res_doc = serialize_doc(doc)
    res_doc.pop("_id", None)
    return {
        "status": "success",
        "message": "Enrolled successfully!",
        "booking_code": booking_code,
        "enrollment": res_doc,
        "booking": res_doc
    }


@app.get("/trip-enrollments")
@app.get("/bookings")
def get_trip_enrollments(
    user_email: Optional[str] = None,
    agent_email: Optional[str] = None,
    trip_id: Optional[str] = None,
    agent_id: Optional[str] = None
):
    or_clauses = []
    if user_email and user_email.strip():
        or_clauses.append({"user_email": {"$regex": f"^{re.escape(user_email.strip())}$", "$options": "i"}})

    if (agent_email and agent_email.strip()) or (agent_id and str(agent_id).strip()):
        ag_emails = set()
        ag_ids = set()
        if agent_email and agent_email.strip():
            raw_em = agent_email.strip().lower()
            ag_emails.add(raw_em)
            ag_user = db.users.find_one({"$or": [
                {"email": {"$regex": f"^{re.escape(raw_em)}$", "$options": "i"}},
                {"username": {"$regex": f"^{re.escape(raw_em)}$", "$options": "i"}}
            ]})
            if ag_user:
                if ag_user.get("email"): ag_emails.add(ag_user.get("email").strip().lower())
                if ag_user.get("username"): ag_emails.add(ag_user.get("username").strip().lower())
            ag_record = db.agents.find_one({"$or": [
                {"email": {"$regex": f"^{re.escape(raw_em)}$", "$options": "i"}},
                {"username": {"$regex": f"^{re.escape(raw_em)}$", "$options": "i"}}
            ]})
            if ag_record:
                if ag_record.get("id"):
                    ag_ids.add(ag_record.get("id"))
                    ag_ids.add(str(ag_record.get("id")))

        if agent_id and str(agent_id).strip():
            try: ag_ids.add(int(agent_id))
            except: pass
            ag_ids.add(str(agent_id).strip())

        # Find all trips owned by this agent
        trip_ids = []
        trip_find_or = []
        for em in ag_emails:
            trip_find_or.append({"agent_email": {"$regex": f"^{re.escape(em)}$", "$options": "i"}})
        for aid in ag_ids:
            trip_find_or.append({"agent_id": aid})
        if trip_find_or:
            for t in db.group_trips.find({"$or": trip_find_or}):
                t_id = t.get("id")
                if t_id is not None:
                    trip_ids.append(t_id)
                    try: trip_ids.append(int(t_id))
                    except: pass
                    trip_ids.append(str(t_id))

        agent_clause = []
        for em in ag_emails:
            agent_clause.append({"agent_email": {"$regex": f"^{re.escape(em)}$", "$options": "i"}})
        for aid in ag_ids:
            agent_clause.append({"agent_id": aid})
        for tid in trip_ids:
            agent_clause.append({"trip_id": tid})

        if agent_clause:
            or_clauses.append({"$or": agent_clause})

    if trip_id is not None and str(trip_id).strip():
        t_id_clean = str(trip_id).strip()
        t_clause = [{"trip_id": t_id_clean}]
        try: t_clause.append({"trip_id": int(t_id_clean)})
        except: pass
        or_clauses.append({"$or": t_clause})

    filt = {"$and": or_clauses} if or_clauses else {}

    # Query from BOTH trip_enrollments AND bookings collections, deduplicate
    rows_enr = list(db.trip_enrollments.find(filt).sort("id", -1))
    rows_bk = list(db.bookings.find(filt).sort("id", -1))

    seen_codes = set()
    enrollments = []
    for r in rows_enr + rows_bk:
        key = str(r.get("booking_code") or r.get("id"))
        if key not in seen_codes:
            seen_codes.add(key)
            d = serialize_doc(r)
            d.pop("_id", None)
            enrollments.append(d)

    return {"status": "success", "enrollments": enrollments, "bookings": enrollments}


@app.post("/cancel-enrollment")
def cancel_enrollment(req: CancelEnrollmentRequest):
    or_clauses = []
    if req.enrollment_id:
        or_clauses.append({"id": req.enrollment_id})
        try: or_clauses.append({"id": int(req.enrollment_id)})
        except: pass
    if req.booking_code:
        b_clean = req.booking_code.strip()
        or_clauses.append({"booking_code": b_clean})
        or_clauses.append({"booking_code": {"$regex": f"^{re.escape(b_clean)}$", "$options": "i"}})
    
    if not or_clauses:
        raise HTTPException(status_code=400, detail="Booking code or enrollment ID is required.")
    
    enr = db.trip_enrollments.find_one({"$or": or_clauses}) or db.bookings.find_one({"$or": or_clauses})
    if not enr:
        raise HTTPException(status_code=404, detail="Enrollment record not found.")
    
    trip_id = enr.get("trip_id")
    seats = enr.get("seats", 1)
    b_code = enr.get("booking_code")
    e_id = enr.get("id")

    update_filter = []
    if b_code:
        update_filter.append({"booking_code": b_code})
    if e_id:
        update_filter.append({"id": e_id})
    
    cancel_data = {
        "status": "cancelled",
        "cancelled_by": "traveller",
        "cancelled_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    db.trip_enrollments.update_many({"$or": update_filter}, {"$set": cancel_data})
    db.bookings.update_many({"$or": update_filter}, {"$set": cancel_data})
    
    # Recalculate trip enrolled_count based on active confirmed bookings
    if trip_id is not None:
        t_clause = [{"trip_id": trip_id}]
        try: t_clause.append({"trip_id": int(trip_id)})
        except: pass
        try: t_clause.append({"trip_id": str(trip_id)})
        except: pass

        confirmed_records = list(db.trip_enrollments.find({
            "$and": [
                {"$or": t_clause},
                {"status": {"$in": ["confirmed", "Confirmed"]}}
            ]
        }))
        total_seats = sum(int(x.get("seats") or 1) for x in confirmed_records)
        db.group_trips.update_one(
            {"$or": [{"id": trip_id}, {"id": str(trip_id)}]},
            {"$set": {"enrolled_count": total_seats}}
        )

    # Automatically purge cancelled traveller from group chat messages and agent 1-on-1 messages
    u_email = (enr.get("user_email") or req.user_email or "").strip().lower()
    ag_email = (enr.get("agent_email") or "").strip().lower()
    if trip_id is not None and u_email:
        t_clause = [{"trip_id": trip_id}]
        try: t_clause.append({"trip_id": int(trip_id)})
        except: pass
        try: t_clause.append({"trip_id": str(trip_id)})
        except: pass

        db.trip_messages.delete_many({
            "$and": [
                {"$or": t_clause},
                {"sender_email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}}
            ]
        })

    if u_email and ag_email:
        db.buddy_messages.delete_many({
            "$or": [
                {"sender_email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}, "receiver_email": {"$regex": f"^{re.escape(ag_email)}$", "$options": "i"}},
                {"sender_email": {"$regex": f"^{re.escape(ag_email)}$", "$options": "i"}, "receiver_email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}}
            ]
        })

    return {"status": "success", "message": "Enrollment cancelled successfully, and traveller removed from group chat."}


@app.post("/update-booking-status")
@app.post("/confirm-booking")
def update_booking_status(req: UpdateBookingStatusRequest):
    or_clauses = []
    if req.enrollment_id:
        or_clauses.append({"id": req.enrollment_id})
        try: or_clauses.append({"id": int(req.enrollment_id)})
        except: pass
    if req.booking_code:
        b_clean = req.booking_code.strip()
        or_clauses.append({"booking_code": b_clean})
        or_clauses.append({"booking_code": {"$regex": f"^{re.escape(b_clean)}$", "$options": "i"}})

    if not or_clauses:
        raise HTTPException(status_code=400, detail="Booking code or enrollment ID is required.")

    enr = db.trip_enrollments.find_one({"$or": or_clauses}) or db.bookings.find_one({"$or": or_clauses})
    if not enr:
        raise HTTPException(status_code=404, detail="Booking record not found.")

    target_status = (req.status or "confirmed").strip().lower()
    if target_status not in ["confirmed", "unconfirmed", "cancelled", "pending"]:
        target_status = "confirmed"

    # If the traveller cancelled their reservation by themselves, agent cannot confirm it
    if target_status == "confirmed":
        if enr.get("cancelled_by") == "traveller" or (enr.get("status") or "").lower() == "cancelled":
            raise HTTPException(
                status_code=400,
                detail="This reservation was cancelled by the traveller and cannot be re-confirmed by the agent."
            )

    b_code = enr.get("booking_code")
    e_id = enr.get("id")
    trip_id = enr.get("trip_id")

    update_filter = []
    if b_code:
        update_filter.append({"booking_code": b_code})
        update_filter.append({"booking_code": {"$regex": f"^{re.escape(b_code)}$", "$options": "i"}})
    if e_id:
        update_filter.append({"id": e_id})
        try: update_filter.append({"id": int(e_id)})
        except: pass

    update_doc = {
        "status": target_status,
        "status_updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    if req.note:
        update_doc["agent_note"] = req.note

    db.trip_enrollments.update_many({"$or": update_filter}, {"$set": update_doc})
    db.bookings.update_many({"$or": update_filter}, {"$set": update_doc})

    # Recalculate trip enrolled_count based on active confirmed bookings
    if trip_id is not None:
        t_clause = [{"trip_id": trip_id}]
        try: t_clause.append({"trip_id": int(trip_id)})
        except: pass
        try: t_clause.append({"trip_id": str(trip_id)})
        except: pass

        confirmed_records = list(db.trip_enrollments.find({
            "$and": [
                {"$or": t_clause},
                {"status": {"$in": ["confirmed", "Confirmed"]}}
            ]
        }))
        total_seats = sum(int(x.get("seats") or 1) for x in confirmed_records)
        db.group_trips.update_one(
            {"$or": [{"id": trip_id}, {"id": str(trip_id)}]},
            {"$set": {"enrolled_count": total_seats}}
        )

    # When unconfirmed or cancelled, automatically remove traveller from group chat messages and agent thread
    if target_status in ["unconfirmed", "cancelled"]:
        u_email = (enr.get("user_email") or "").strip().lower()
        ag_email = (enr.get("agent_email") or req.agent_email or "").strip().lower()
        if trip_id is not None and u_email:
            t_clause = [{"trip_id": trip_id}]
            try: t_clause.append({"trip_id": int(trip_id)})
            except: pass
            try: t_clause.append({"trip_id": str(trip_id)})
            except: pass

            db.trip_messages.delete_many({
                "$and": [
                    {"$or": t_clause},
                    {"sender_email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}}
                ]
            })

        if u_email and ag_email:
            db.buddy_messages.delete_many({
                "$or": [
                    {"sender_email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}, "receiver_email": {"$regex": f"^{re.escape(ag_email)}$", "$options": "i"}},
                    {"sender_email": {"$regex": f"^{re.escape(ag_email)}$", "$options": "i"}, "receiver_email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}}
                ]
            })

    email_res = {"success": False, "detail": "Status updated without email dispatch"}
    if target_status == "confirmed":
        # Send confirmation email from agent to traveller
        email_res = send_booking_confirmation_email(
            booking_doc=enr,
            agent_email=req.agent_email,
            agent_name=req.agent_name,
            agent_note=req.note
        )

    updated_enr = db.trip_enrollments.find_one({"$or": update_filter}) or db.bookings.find_one({"$or": update_filter})
    serialized = serialize_doc(updated_enr) if updated_enr else {}
    serialized.pop("_id", None)

    return {
        "status": "success",
        "message": f"Booking successfully marked as {target_status}.",
        "booking_code": b_code,
        "new_status": target_status,
        "booking": serialized,
        "email_sent": email_res.get("success", False),
        "email_detail": email_res.get("detail", "")
    }


@app.post("/contact-agent")
@app.post("/submit-query")
def contact_agent(req: ContactAgentRequest):
    inquiry_id = get_next_sequence("agent_inquiries")

    # Resolve trip details if trip_id or trip_title or message mentions trip
    trip = None
    if req.trip_id:
        trip = db.group_trips.find_one({"$or": [{"id": req.trip_id}, {"id": str(req.trip_id)}]})

    msg_raw = (req.message or req.message_text or "").strip()

    if not trip and req.trip_title and req.trip_title.strip():
        trip = db.group_trips.find_one({"title": {"$regex": f"^{re.escape(req.trip_title.strip())}$", "$options": "i"}})

    if not trip and msg_raw:
        for t in db.group_trips.find({}):
            t_title = (t.get("title") or "").strip()
            if t_title and t_title.lower() in msg_raw.lower():
                trip = t
                break

    trip_id = trip.get("id") if trip else req.trip_id
    trip_title = trip.get("title", "") if trip else (req.trip_title or "")
    dest = (req.destination or "").strip() or (trip.get("destination", "") if trip else "")

    agent_id = req.agent_id or (trip.get("agent_id") if trip else 0)
    agent_name = (req.agent_name or "").strip() or (trip.get("agent_name", "") if trip else "")
    agent_email = (req.agent_email or "").strip().lower() or (trip.get("agent_email", "").lower() if trip else "")

    if not agent_email and agent_id:
        ag = db.agents.find_one({"$or": [{"id": agent_id}, {"id": str(agent_id)}]})
        if ag:
            agent_email = (ag.get("email") or "").strip().lower()
            agent_name = agent_name or ag.get("agent_name", "")

    doc = {
        "id": inquiry_id,
        "agent_id": agent_id or 0,
        "agent_name": agent_name,
        "agent_email": agent_email,
        "user_email": req.user_email.strip().lower(),
        "user_name": req.user_name.strip(),
        "user_phone": (req.user_phone or "").strip(),
        "inquiry_type": req.inquiry_type or req.reason or "general",
        "trip_id": trip_id,
        "trip_title": trip_title,
        "destination": dest,
        "travel_dates": req.travel_dates or req.expected_dates or "",
        "budget": req.budget or "",
        "group_size": req.group_size or "1",
        "message": msg_raw,
        "status": "pending",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    # Store in BOTH agent_inquiries AND queries collections in MongoDB
    db.agent_inquiries.insert_one(doc)
    doc_copy = dict(doc)
    doc_copy.pop("_id", None)
    db.queries.insert_one(doc_copy)

    res_doc = serialize_doc(doc)
    res_doc.pop("_id", None)
    return {
        "status": "success",
        "message": "Inquiry sent successfully to the agent!",
        "inquiry": res_doc,
        "query": res_doc
    }


@app.get("/agent-inquiries")
@app.get("/queries")
def get_agent_inquiries(
    agent_email: Optional[str] = None,
    agent_id: Optional[str] = None,
    trip_id: Optional[str] = None
):
    or_clauses = []

    if (agent_email and agent_email.strip()) or (agent_id and str(agent_id).strip()):
        ag_emails = set()
        ag_ids = set()
        if agent_email and agent_email.strip():
            raw_em = agent_email.strip().lower()
            ag_emails.add(raw_em)
            ag_user = db.users.find_one({"$or": [
                {"email": {"$regex": f"^{re.escape(raw_em)}$", "$options": "i"}},
                {"username": {"$regex": f"^{re.escape(raw_em)}$", "$options": "i"}}
            ]})
            if ag_user:
                if ag_user.get("email"): ag_emails.add(ag_user.get("email").strip().lower())
                if ag_user.get("username"): ag_emails.add(ag_user.get("username").strip().lower())
            ag_record = db.agents.find_one({"$or": [
                {"email": {"$regex": f"^{re.escape(raw_em)}$", "$options": "i"}},
                {"username": {"$regex": f"^{re.escape(raw_em)}$", "$options": "i"}}
            ]})
            if ag_record:
                if ag_record.get("id"):
                    ag_ids.add(ag_record.get("id"))
                    ag_ids.add(str(ag_record.get("id")))

        if agent_id and str(agent_id).strip():
            try: ag_ids.add(int(agent_id))
            except: pass
            ag_ids.add(str(agent_id).strip())

        # Find all trips owned by this agent
        trip_ids = []
        trip_find_or = []
        for em in ag_emails:
            trip_find_or.append({"agent_email": {"$regex": f"^{re.escape(em)}$", "$options": "i"}})
        for aid in ag_ids:
            trip_find_or.append({"agent_id": aid})
        if trip_find_or:
            for t in db.group_trips.find({"$or": trip_find_or}):
                t_id = t.get("id")
                if t_id is not None:
                    trip_ids.append(t_id)
                    try: trip_ids.append(int(t_id))
                    except: pass
                    trip_ids.append(str(t_id))

        agent_clause = []
        for em in ag_emails:
            agent_clause.append({"agent_email": {"$regex": f"^{re.escape(em)}$", "$options": "i"}})
        for aid in ag_ids:
            agent_clause.append({"agent_id": aid})
        for tid in trip_ids:
            agent_clause.append({"trip_id": tid})

        if agent_clause:
            or_clauses.append({"$or": agent_clause})

    if trip_id is not None and str(trip_id).strip():
        t_id_clean = str(trip_id).strip()
        t_clause = [{"trip_id": t_id_clean}]
        try: t_clause.append({"trip_id": int(t_id_clean)})
        except: pass
        or_clauses.append({"$or": t_clause})

    filt = {"$and": or_clauses} if or_clauses else {}

    # Query from BOTH agent_inquiries AND queries collections, deduplicate
    rows_inq = list(db.agent_inquiries.find(filt).sort("id", -1))
    rows_q = list(db.queries.find(filt).sort("id", -1))

    seen_ids = set()
    inquiries = []
    for r in rows_inq + rows_q:
        qid = r.get("id")
        if qid not in seen_ids:
            seen_ids.add(qid)
            d = serialize_doc(r)
            d.pop("_id", None)
            inquiries.append(d)

    return {"status": "success", "inquiries": inquiries, "queries": inquiries}


@app.post("/update-agent-inquiry-status")
def update_agent_inquiry_status(req: UpdateInquiryStatusRequest):
    inq = db.agent_inquiries.find_one({"id": req.inquiry_id}) or db.queries.find_one({"id": req.inquiry_id})
    if not inq:
        raise HTTPException(status_code=404, detail="Inquiry not found.")
    db.agent_inquiries.update_one({"id": req.inquiry_id}, {"$set": {"status": req.status}})
    db.queries.update_one({"id": req.inquiry_id}, {"$set": {"status": req.status}})
    return {"status": "success", "message": f"Inquiry status updated to {req.status}."}

@app.post("/answer-query")
@app.post("/reply-agent-inquiry")
def answer_query(req: AnswerQueryRequest):
    inq = db.agent_inquiries.find_one({"id": req.inquiry_id}) or db.queries.find_one({"id": req.inquiry_id})
    if not inq:
        raise HTTPException(status_code=404, detail="Query / Inquiry not found.")
    
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    now_local = time.localtime()
    time_str = time.strftime("%I:%M %p", now_local).lstrip('0')

    update_fields = {
        "reply_text": req.reply_text.strip(),
        "status": "answered",
        "replied_at": now_iso,
        "replied_time_str": time_str,
        "replied_by_name": req.agent_name,
        "replied_by_email": req.agent_email
    }

    db.agent_inquiries.update_one({"id": req.inquiry_id}, {"$set": update_fields})
    db.queries.update_one({"id": req.inquiry_id}, {"$set": update_fields})

    # Record reply into buddy_messages so traveller can see it too
    user_email = (inq.get("user_email") or "").strip().lower()
    agent_email = (req.agent_email or inq.get("agent_email") or "").strip().lower()
    if user_email and agent_email:
        msg_id = get_next_sequence("buddy_messages")
        trip_label = inq.get("trip_title") or inq.get("destination") or "Trip"
        reply_msg_text = f"[Answer to Inquiry for {trip_label}]: {req.reply_text.strip()}"
        doc = {
            "id": msg_id,
            "sender_email": agent_email,
            "receiver_email": user_email,
            "message_text": reply_msg_text,
            "time_str": time_str,
            "status": "delivered",
            "created_at": now_iso
        }
        db.buddy_messages.insert_one(doc)

    return {"status": "success", "message": "Query answered successfully and stored in MongoDB."}


@app.get("/trip-interests/{user_email}")
def get_trip_interests(user_email: str):
    email_clean = user_email.strip().lower()
    rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}
    
    or_clauses = [{"user_email": rx}]
    user = db.users.find_one({"$or": [{"email": rx}, {"username": rx}]})
    if user:
        u_email = (user.get("email") or "").strip().lower()
        u_uname = (user.get("username") or "").strip().lower()
        if u_email:
            or_clauses.append({"user_email": {"$regex": f"^{re.escape(u_email)}$", "$options": "i"}})
        if u_uname:
            or_clauses.append({"user_email": {"$regex": f"^{re.escape(u_uname)}$", "$options": "i"}})

    rows = list(db.trip_interests.find({"$or": or_clauses}).sort("id", -1))
    res = []
    seen_ids = set()
    for r in rows:
        d = serialize_doc(r)
        d.pop("_id", None)
        if d.get("id") not in seen_ids:
            seen_ids.add(d.get("id"))
            res.append(d)
    return {"status": "success", "interests": res}



@app.post("/add-trip-interest")
def add_trip_interest(req: AddTripInterestRequest):
    user_email = (req.user_email or "").strip().lower()
    destination = (req.destination or "").strip()
    preferred_dates = (req.preferred_dates or "").strip()
    budget = (req.budget or "").strip()
    notes = (req.notes or "").strip()

    interest_id = get_next_sequence("trip_interests")
    doc = {
        "id": interest_id,
        "user_email": user_email,
        "destination": destination,
        "preferred_dates": preferred_dates,
        "budget": budget,
        "notes": notes,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    db.trip_interests.insert_one(doc)
    sync_user_trip_interests_field(user_email)
    return {"status": "success", "message": "Trip interest added successfully", "id": interest_id}


@app.post("/edit-trip-interest")
def edit_trip_interest(req: EditTripInterestRequest):
    user_email = (req.user_email or "").strip().lower()
    email_rx = {"$regex": f"^{re.escape(user_email)}$", "$options": "i"}
    destination = (req.destination or "").strip()
    preferred_dates = (req.preferred_dates or "").strip()
    budget = (req.budget or "").strip()
    notes = (req.notes or "").strip()

    db.trip_interests.update_one(
        {"id": req.id, "user_email": email_rx},
        {"$set": {
            "destination": destination,
            "preferred_dates": preferred_dates,
            "budget": budget,
            "notes": notes
        }}
    )
    sync_user_trip_interests_field(user_email)
    return {"status": "success", "message": "Trip interest updated successfully"}


@app.post("/delete-trip-interest")
def delete_trip_interest(req: DeleteTripInterestRequest):
    email_clean = (req.user_email or "").strip().lower()
    email_rx = {"$regex": f"^{re.escape(email_clean)}$", "$options": "i"}
    db.trip_interests.delete_one({"id": req.id, "user_email": email_rx})
    sync_user_trip_interests_field(email_clean)
    return {"status": "success", "message": "Trip interest deleted successfully"}


@app.post("/send-connection-request")
def send_connection_request(req: ConnectionRequestModel):
    sender = (req.sender_email or "").strip().lower()
    receiver = (req.receiver_email or "").strip().lower()

    if not sender or not receiver:
        raise HTTPException(status_code=400, detail="Sender and receiver emails are required.")

    s_rx = {"$regex": f"^{re.escape(sender)}$", "$options": "i"}
    r_rx = {"$regex": f"^{re.escape(receiver)}$", "$options": "i"}

    s_user = db.users.find_one({"$or": [{"email": s_rx}, {"username": s_rx}]})
    if s_user:
        sender = (s_user.get("email") or sender).strip().lower()

    r_user = db.users.find_one({"$or": [{"email": r_rx}, {"username": r_rx}]})
    if r_user:
        receiver = (r_user.get("email") or receiver).strip().lower()

    if sender == receiver:
        raise HTTPException(status_code=400, detail="You cannot connect with your own account.")

    s_clean_rx = {"$regex": f"^{re.escape(sender)}$", "$options": "i"}
    r_clean_rx = {"$regex": f"^{re.escape(receiver)}$", "$options": "i"}

    existing = db.connections.find_one({
        "$or": [
            {"sender_email": s_clean_rx, "receiver_email": r_clean_rx},
            {"sender_email": r_clean_rx, "receiver_email": s_clean_rx}
        ]
    })

    if existing:
        db.connections.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "status": "pending",
                "message": req.message or "",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }}
        )
        conn_id = existing.get("id")
    else:
        conn_id = get_next_sequence("connections")
        doc = {
            "id": conn_id,
            "sender_email": sender,
            "receiver_email": receiver,
            "message": req.message or "",
            "status": "pending",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        db.connections.insert_one(doc)

    return {"status": "success", "message": "Connection request sent successfully.", "id": conn_id}


@app.post("/respond-connection-request")
def respond_connection_request(req: RespondConnectionRequest):
    stat = (req.status or "").strip().lower()
    if stat not in ["accepted", "declined", "withdrawn"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be accepted, declined, or withdrawn.")

    if stat in ["declined", "withdrawn"]:
        db.connections.delete_many({"id": req.connection_id})
        return {"status": "success", "message": f"Connection request {stat}."}

    db.connections.update_one({"id": req.connection_id}, {"$set": {"status": stat}})
    return {"status": "success", "message": f"Connection request {stat}."}


@app.post("/withdraw-connection-request")
def withdraw_connection_request(req: WithdrawConnectionRequest):
    if req.connection_id:
        db.connections.delete_many({"id": req.connection_id})
    elif req.sender_email and req.receiver_email:
        s_rx = {"$regex": f"^{re.escape(req.sender_email.strip().lower())}$", "$options": "i"}
        r_rx = {"$regex": f"^{re.escape(req.receiver_email.strip().lower())}$", "$options": "i"}
        db.connections.delete_many({"sender_email": s_rx, "receiver_email": r_rx})
    return {"status": "success", "message": "Connection request withdrawn successfully."}


@app.get("/user-connections/{email}")
def get_user_connections(email: str):
    clean_query = (email or "").strip().lower()
    rx = {"$regex": f"^{re.escape(clean_query)}$", "$options": "i"}

    # Look up user details
    user = db.users.find_one({"$or": [{"email": rx}, {"username": rx}]})
    user_emails = [clean_query]
    if user:
        if user.get("email"):
            user_emails.append(user["email"].strip().lower())
        if user.get("username"):
            user_emails.append(user["username"].strip().lower())

    recv_or = [{"receiver_email": {"$regex": f"^{re.escape(e)}$", "$options": "i"}} for e in set(user_emails)]
    send_or = [{"sender_email": {"$regex": f"^{re.escape(e)}$", "$options": "i"}} for e in set(user_emails)]

    # 1. Received Pending Requests
    pending_docs = list(db.connections.find({
        "$or": recv_or,
        "status": "pending"
    }).sort("id", -1))

    pending = []
    for c in pending_docs:
        c_dict = serialize_doc(c)
        c_dict.pop("_id", None)
        s_email = c_dict.get("sender_email", "")
        s_rx = {"$regex": f"^{re.escape(s_email)}$", "$options": "i"}
        u = db.users.find_one({"$or": [{"email": s_rx}, {"username": s_rx}]})
        if u:
            c_dict["first_name"] = u.get("first_name", "")
            c_dict["last_name"] = u.get("last_name", "")
            c_dict["username"] = u.get("username", "")
            c_dict["profile_pic"] = u.get("profile_pic", "")
        pending.append(c_dict)

    # 2. Sent Pending Requests
    sent_docs = list(db.connections.find({
        "$or": send_or,
        "status": "pending"
    }).sort("id", -1))

    sent_requests = []
    for c in sent_docs:
        c_dict = serialize_doc(c)
        c_dict.pop("_id", None)
        r_email = c_dict.get("receiver_email", "")
        r_rx = {"$regex": f"^{re.escape(r_email)}$", "$options": "i"}
        u = db.users.find_one({"$or": [{"email": r_rx}, {"username": r_rx}]})
        if u:
            c_dict["receiver_first_name"] = u.get("first_name", "")
            c_dict["receiver_last_name"] = u.get("last_name", "")
            c_dict["receiver_username"] = u.get("username", "")
            c_dict["receiver_profile_pic"] = u.get("profile_pic", "")
        sent_requests.append(c_dict)

    # 3. Accepted Buddies
    buddies_docs = list(db.connections.find({
        "$or": recv_or + send_or,
        "status": "accepted"
    }).sort("id", -1))

    buddies = []
    for c in buddies_docs:
        c_dict = serialize_doc(c)
        c_dict.pop("_id", None)
        s_email = (c_dict.get("sender_email") or "").strip().lower()
        if s_email in [e.lower() for e in user_emails]:
            other_email = c_dict.get("receiver_email", "")
        else:
            other_email = c_dict.get("sender_email", "")
        
        c_dict["buddy_email"] = other_email
        other_rx = {"$regex": f"^{re.escape(other_email)}$", "$options": "i"}
        u = db.users.find_one({"$or": [{"email": other_rx}, {"username": other_rx}]})
        if u:
            c_dict["buddy_name"] = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or u.get("username")
            c_dict["buddy_username"] = u.get("username", "")
            c_dict["buddy_pic"] = u.get("profile_pic", "")
        buddies.append(c_dict)

    return {
        "status": "success",
        "pending_requests": pending,
        "sent_requests": sent_requests,
        "accepted_buddies": buddies
    }


class BuddyMessageRequest(BaseModel):
    sender_email: str
    receiver_email: str
    message_text: str



@app.post("/send-trip-message")
def send_trip_message(req: SendTripMessageRequest):
    text = (req.message_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message text is required.")

    sender_role = req.sender_role or "agent"
    sender_email = (req.sender_email or "").strip().lower()

    # If sender is a traveller, strictly verify they have an active confirmed reservation
    if sender_role != "agent":
        t_clause = [{"trip_id": req.trip_id}]
        try: t_clause.append({"trip_id": int(req.trip_id)})
        except: pass
        try: t_clause.append({"trip_id": str(req.trip_id)})
        except: pass

        has_booking = db.trip_enrollments.find_one({
            "$and": [
                {"$or": t_clause},
                {"user_email": {"$regex": f"^{re.escape(sender_email)}$", "$options": "i"}},
                {"status": {"$in": ["confirmed", "Confirmed"]}}
            ]
        })
        if not has_booking:
            raise HTTPException(
                status_code=403,
                detail="Your reservation for this departure is cancelled or unconfirmed. Group chat access is restricted."
            )

    trip = db.group_trips.find_one({"$or": [{"id": req.trip_id}, {"id": str(req.trip_id)}]})
    trip_title = trip.get("title", "") if trip else f"Trip #{req.trip_id}"

    msg_id = get_next_sequence("trip_messages")
    now_local = time.localtime()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    time_str = time.strftime("%I:%M %p", now_local).lstrip('0')

    doc = {
        "id": msg_id,
        "trip_id": req.trip_id,
        "trip_title": trip_title,
        "sender_email": (req.sender_email or "").strip().lower(),
        "sender_name": (req.sender_name or "Host Guide").strip(),
        "sender_role": req.sender_role or "agent",
        "message_text": text,
        "time_str": time_str,
        "status": "delivered",
        "created_at": now_iso
    }

    db.trip_messages.insert_one(doc)
    doc_out = serialize_doc(doc)
    doc_out.pop("_id", None)
    return {"status": "success", "message": doc_out}


@app.get("/get-trip-messages/{trip_id}")
def get_trip_messages(trip_id: int):
    t_clause = [{"trip_id": trip_id}]
    try: t_clause.append({"trip_id": str(trip_id)})
    except: pass

    # Get all active confirmed traveller emails for this trip
    confirmed_records = list(db.trip_enrollments.find({
        "$and": [
            {"$or": t_clause},
            {"status": {"$in": ["confirmed", "Confirmed"]}}
        ]
    }))
    active_emails = {str(e.get("user_email", "")).strip().lower() for e in confirmed_records if e.get("user_email")}

    rows = list(db.trip_messages.find({"$or": t_clause}).sort("id", 1))
    msgs = []
    for r in rows:
        s_role = r.get("sender_role", "agent")
        s_email = str(r.get("sender_email", "")).strip().lower()
        # If message was sent by a traveller who cancelled, omit it from the group feed
        if s_role != "agent" and s_email not in active_emails:
            continue
        d = serialize_doc(r)
        d.pop("_id", None)
        msgs.append(d)
    return {"status": "success", "messages": msgs}


@app.get("/trip-travellers/{trip_id}")
def get_trip_travellers(trip_id: int):
    t_clause = [{"trip_id": trip_id}]
    try: t_clause.append({"trip_id": str(trip_id)})
    except: pass
    
    active_filt = {"$and": [{"$or": t_clause}, {"status": {"$in": ["confirmed", "Confirmed"]}}]}
    rows_enr = list(db.trip_enrollments.find(active_filt))
    rows_bk = list(db.bookings.find(active_filt))
    
    seen = set()
    travellers = []
    for r in rows_enr + rows_bk:
        key = str(r.get("booking_code") or r.get("id"))
        if key not in seen:
            seen.add(key)
            name = (r.get("user_name") or "Traveller").strip()
            seats = r.get("seats", 1)
            raw_names = r.get("traveller_names")
            if not raw_names or not isinstance(raw_names, list) or len(raw_names) == 0:
                raw_names = [name]
            # ONLY return name and pax count - DO NOT return emails or phone numbers for privacy
            travellers.append({
                "name": name,
                "seats": seats,
                "traveller_names": raw_names
            })
    return {
        "status": "success",
        "trip_id": trip_id,
        "travellers": travellers,
        "total_pax": sum(t.get("seats", 1) for t in travellers)
    }

@app.post("/send-buddy-message")
def send_buddy_message(payload: BuddyMessageRequest):
    sender = (payload.sender_email or "").strip().lower()
    receiver = (payload.receiver_email or "").strip().lower()
    text = (payload.message_text or "").strip()

    if not sender or not receiver or not text:
        raise HTTPException(status_code=400, detail="Sender, receiver, and message text are required.")

    msg_id = get_next_sequence("buddy_messages")
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    now_local = time.localtime()
    time_str = time.strftime("%I:%M %p", now_local).lstrip('0')
    doc = {
        "id": msg_id,
        "sender_email": sender,
        "receiver_email": receiver,
        "message_text": text,
        "time_str": time_str,
        "status": "delivered",
        "created_at": now_iso
    }

    db.buddy_messages.insert_one(doc)
    doc_out = serialize_doc(doc)
    doc_out.pop("_id", None)
    return {"status": "success", "message": doc_out}


@app.get("/get-buddy-messages/{user_email}/{buddy_email}")
def get_buddy_messages(user_email: str, buddy_email: str):
    u1 = (user_email or "").strip().lower()
    u2 = (buddy_email or "").strip().lower()

    if not u1 or not u2:
        return {"status": "success", "messages": []}

    u1_rx = {"$regex": f"^{re.escape(u1)}$", "$options": "i"}
    u2_rx = {"$regex": f"^{re.escape(u2)}$", "$options": "i"}

    u1_doc = db.users.find_one({"$or": [{"email": u1_rx}, {"username": u1_rx}]})
    u2_doc = db.users.find_one({"$or": [{"email": u2_rx}, {"username": u2_rx}]})

    u1_keys = [u1]
    if u1_doc:
        if u1_doc.get("email"): u1_keys.append(u1_doc["email"].strip().lower())
        if u1_doc.get("username"): u1_keys.append(u1_doc["username"].strip().lower())

    u2_keys = [u2]
    if u2_doc:
        if u2_doc.get("email"): u2_keys.append(u2_doc["email"].strip().lower())
        if u2_doc.get("username"): u2_keys.append(u2_doc["username"].strip().lower())

    u1_keys = list(set(u1_keys))
    u2_keys = list(set(u2_keys))

    match_or = []
    for k1 in u1_keys:
        for k2 in u2_keys:
            r1 = {"$regex": f"^{re.escape(k1)}$", "$options": "i"}
            r2 = {"$regex": f"^{re.escape(k2)}$", "$options": "i"}
            match_or.append({"sender_email": r1, "receiver_email": r2})
            match_or.append({"sender_email": r2, "receiver_email": r1})

    docs = list(db.buddy_messages.find({"$or": match_or}).sort("id", 1))

    cleaned = []
    for d in docs:
        c = serialize_doc(d)
        c.pop("_id", None)
        cleaned.append(c)

    return {"status": "success", "messages": cleaned}




class ChatAiAssistantRequest(BaseModel):
    query: str
    traveller_name: Optional[str] = "Traveller"
    traveller_email: Optional[str] = ""
    agent_name: Optional[str] = "Travel Agent"
    agent_agency: Optional[str] = "Travel Agency"
    trip_title: Optional[str] = ""
    destination: Optional[str] = ""
    travel_dates: Optional[str] = ""
    budget: Optional[str] = ""
    group_size: Optional[str] = "1"
    inquiry_message: Optional[str] = ""
    recent_messages: Optional[List[dict]] = []
    sender_role: Optional[str] = "agent"  # 'agent' or 'traveller'


@app.post("/chat-ai-assistant")
def chat_ai_assistant(req: ChatAiAssistantRequest):
    """
    Context-aware AI Copilot connected to the agent-traveller chat.
    Understands trip title, destination, dates, budget, group size, and recent chat history
    so neither the agent nor traveller has to repeat the context.
    """
    q = (req.query or "").strip().lower()
    dest = req.destination or req.trip_title or "your destination"
    traveller = req.traveller_name or "the traveller"
    agent = req.agent_name or "the host agent"
    agency = req.agent_agency or "Travel Agency"
    dates = req.travel_dates or "upcoming travel season"
    budget = req.budget or "flexible budget"
    grp = req.group_size or "group"
    role = (req.sender_role or "agent").lower()

    # Extract last few messages for conversational context
    recent_text = ""
    if req.recent_messages:
        snippets = []
        for m in req.recent_messages[-6:]:
            s_name = m.get("sender_email", "User")
            m_text = m.get("message_text", "")
            snippets.append(f"{s_name}: {m_text}")
        recent_text = " | ".join(snippets)

    # 1. Try Groq or Gemini API if key is available in environment
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            import urllib.request
            import json as py_json
            sys_prompt = (
                f"You are the TravelVerse AI Copilot assisting in a live chat between travel agent '{agent}' ({agency}) "
                f"and client '{traveller}'. Trip: '{req.trip_title or dest}', Destination: '{dest}', Dates: '{dates}', "
                f"Group: '{grp}', Budget: '{budget}'. Recent conversation: '{recent_text}'. "
                f"Provide concise, practical, professional travel guidance or ready-to-send messages directly addressing the user's request."
            )
            data_payload = {
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": req.query}
                ],
                "temperature": 0.6,
                "max_tokens": 450
            }
            req_post = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=py_json.dumps(data_payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {groq_key}"
                }
            )
            with urllib.request.urlopen(req_post, timeout=6) as response:
                res_data = py_json.loads(response.read().decode())
                ai_text = res_data["choices"][0]["message"]["content"].strip()
                if ai_text:
                    return {"status": "success", "reply": ai_text, "source": "groq"}
        except Exception as e:
            pass # Fall through to intelligent local context generator

    # 2. Intelligent Context-Aware Engine
    reply = ""

    inq_note = req.inquiry_message or "Looking for personalized itinerary details and pricing."
    trip_dep = req.trip_title or "Custom Expedition"
    if "summar" in q or "inquir" in q or "context" in q or "overview" in q:
        reply = (
            f"📋 **Trip & Client Summary for {traveller}:**\n\n"
            f"• **Destination:** {dest}\n"
            f"• **Trip Departure:** {trip_dep}\n"
            f"• **Travel Dates:** {dates}\n"
            f"• **Party Size:** {grp} traveller(s)\n"
            f"• **Budget:** {budget}\n"
            f"• **Client Note:** '{inq_note}'\n\n"
            f"💡 **Recommendation:** Confirm date flexibility and offer accommodation upgrades (e.g. boutique homestay vs camp) to lock in the reservation."
        )
    elif "itinerar" in q or "day" in q or "schedule" in q or "plan" in q:
        reply = (
            f"🗺️ **Suggested 3-Day Outline for {dest} ({grp} travellers):**\n\n"
            f"• **Day 1: Arrival & Acclimatization** — Check-in, welcome orientation with {agent}, easy local walk and traditional local dinner.\n"
            f"• **Day 2: Core Highlights & Adventure** — Guided tour of iconic viewpoints and cultural landmarks; scenic picnic lunch; sunset photography session.\n"
            f"• **Day 3: Immersive Heritage & Departure** — Morning artisan market visit, farewell tea ceremony, and seamless airport/station transfer.\n\n"
            f"*(Customizable based on {traveller}'s fitness level and pace preferences.)*"
        )
    elif "weather" in q or "climat" in q or "temp" in q or "season" in q:
        reply = (
            f"🌤️ **Weather & Packing Brief for {dest} ({dates}):**\n\n"
            f"• **Expected Conditions:** Pleasant daytime temperatures (approx. 18°C – 24°C), cooler evenings dropping to 8°C – 12°C.\n"
            f"• **Clothing Advice:** Pack layered breathable garments, sturdy walking shoes with ankle support, and a lightweight windproof/water-resistant jacket.\n"
            f"• **Essentials:** UV sunglasses, high-SPF sunscreen, personal water purification bottle, and power bank for mountain trails."
        )
    elif "cost" in q or "price" in q or "quote" in q or "budget" in q or "inclus" in q:
        reply = (
            f"💰 **Customized Estimate & Inclusions for {traveller} ({grp} pax):**\n\n"
            f"• **Estimated Package Total:** {budget if '$' in budget or '₹' in budget else '$850 – $1,150 per person'}\n"
            f"• **Includes:** 4x4 private transport throughout, certified mountain/cultural guide ({agency}), all permits & entry passes, boutique stay with breakfast & dinner.\n"
            f"• **Excludes:** Personal expenses, optional tips, and personal insurance.\n\n"
            f"💡 Tip: Offer a 5% early booking discount if deposit is secured within 48 hours."
        )
    elif "draft" in q or "reply" in q or "respond" in q or "message" in q:
        if role == "agent":
            reply = (
                f"Hello {traveller}! 👋 Thank you for connecting with us at {agency}. "
                f"We are excited to help you organize your journey to {dest} for {dates}. "
                f"We can tailor all accommodations, transport, and daily adventures to your group ({grp} travellers). "
                f"Would you like us to finalize the bespoke itinerary or schedule a brief call right here to review any specific preferences?"
            )
        else:
            reply = (
                f"Hi {agent}! 👋 We're really looking forward to the {req.trip_title or dest} trip for {dates}. "
                f"Could you confirm the pick-up timing, gear checklist, and if there are any specific meal arrangements we should prepare for? Thank you!"
            )
    else:
        reply = (
            f"✨ **TravelVerse AI Copilot:**\n"
            f"Regarding '{req.query}' for **{dest}** with **{traveller}**:\n\n"
            f"For trips around **{dates}** with **{grp} traveller(s)** ({budget}), "
            f"we advise confirming advance permits, ensuring acclimatization buffers, and keeping flexible contingencies for weather. "
            f"Both {agent} and {traveller} can click the **Call** button above to connect directly and finalize details in real time."
        )

    return {"status": "success", "reply": reply, "source": "context_engine"}


# Serve static frontend files
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.isdir(frontend_dir):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)



@app.get("/travellers")
def get_travellers():
    """
    Returns all registered travellers from the db.travellers collection.
    """
    docs = list(db.travellers.find({}, {"_id": 0, "password": 0, "otp_code": 0}))
    return {"status": "success", "travellers": docs, "count": len(docs)}
