"""
TravelVerse AI Itinerary & Departure Dossier Generator Engine
Generates executive-grade, comprehensive travel itineraries with day-wise schedules,
inclusions, logistics, packing checklists, and luxury brochure content.
"""

import re
from typing import Dict, Any, List

DESTINATION_PRESETS = {
    "udaipur": {
        "title": "Royal Udaipur & Mewar Kingdom Heritage Circuit",
        "tagline": "An intimate journey through grand lake palaces, sunset boat cruises, and vibrant Mewari artisan bazaars",
        "category": "Cultural & Heritage",
        "season_climate": "October to March (Crisp & Sunny, 15°C – 28°C)",
        "stay_type": "4-Star Heritage Haveli & Lake-view Boutique Suites",
        "transit_mode": "Private Air-Conditioned Coach & Solar-powered Lake Boat",
        "meeting_point": "09:00 AM at Udaipur City Railway Station VIP Lounge / Maharana Pratap Airport",
        "dropoff_point": "05:30 PM at Udaipur Airport / Railway Station",
        "packing_essentials": [
            "Comfortable walking shoes with rubber grip for marble courtyards",
            "Breathable cotton attire with evening light jacket or shawl",
            "Polarized UV sunglasses & wide-brim sun hat",
            "Camera with extra battery / SD card for palace photography",
            "Valid Government-issued Photo ID (Aadhaar / Passport)"
        ],
        "health_advisory": "Moderate walking across palace stairways and cobbled lanes. Advise guide of any mobility or dietary requirements.",
        "inclusions": [
            "All boutique heritage hotel accommodations on twin-sharing basis",
            "Daily royal buffet breakfast & welcome rooftop Mewari dinner",
            "All palace, museum & fort entry tickets with VIP queue bypass",
            "Private sunset solar boat cruise around Jag Mandir Island",
            "Government-certified English & Hindi heritage historian guide",
            "Chauffeur-driven AC ground transport for all transfers & excursions",
            "24/7 on-ground expedition concierge & first-aid wilderness kit"
        ],
        "exclusions": [
            "Airfare or long-distance rail tickets to/from Udaipur",
            "Personal travel, baggage, and medical evacuation insurance",
            "Discretionary tips for palace guides, chauffeurs, and hotel staff",
            "Personal laundry, phone calls, and alcoholic beverages"
        ],
        "days": [
            {
                "title": "Rendezvous, City Palace Odyssey & Sunset Lake Pichola Cruise",
                "activities": "Gather at designated rendezvous point for welcome briefing. Transfer to boutique heritage haveli and check in. Afternoon guided walk through the majestic City Palace complex, exploring the Crystal Gallery and Zenana Mahal. Board an exclusive private solar boat for a golden hour cruise across Lake Pichola, drifting past the Lake Palace towards Jag Mandir Island.",
                "meals": "Welcome Royal Dinner",
                "stay": "Boutique Heritage Haveli, Lake Pichola"
            },
            {
                "title": "Spiritual Shrines, Royal Gardens & Monsoon Palace Sunset Viewpoint",
                "activities": "Morning visit to the intricately carved 1651 Jagdish Temple, observing the morning Aarti ceremony. Stroll through the lush fountains of Saheliyon Ki Bari (Courtyard of the Maidens). Savor traditional Mewari Dal Baati Churma lunch at an iconic heritage courtyard. In late afternoon, ascend through the wildlife sanctuary up to the historic Monsoon Palace (Sajjangarh) for panoramic views of the Aravalli range and lakes.",
                "meals": "Breakfast & Traditional Mewari Lunch",
                "stay": "Boutique Heritage Haveli, Lake Pichola"
            },
            {
                "title": "Artisan Bazaars, Bagore Ki Haveli & Departure Farewell",
                "activities": "Morning heritage craft exploration through Hathi Pol and Bada Bazaar, discovering authentic miniature paintings, silver jewelry, and handcrafted pottery. Midday visit to Bagore Ki Haveli on Gangaur Ghat. Enjoy a farewell tea at an open-terrace cafe overlooking Fateh Sagar Lake before our private transfer coordinates return departures.",
                "meals": "Breakfast & Farewell High Tea",
                "stay": "Expedition Concludes / Transfer to Airport"
            },
            {
                "title": "Excursion to Fortress of Kumbhalgarh (The Great Wall of India)",
                "activities": "Scenic morning drive through the Aravalli highlands to UNESCO World Heritage Kumbhalgarh Fort. Walk atop the second-longest continuous wall in the world and tour Badal Mahal palace. Return via rural craft villages.",
                "meals": "Breakfast & Village Picnic Lunch",
                "stay": "Boutique Heritage Haveli, Lake Pichola"
            },
            {
                "title": "Marble Marvels of Ranakpur Jain Temples & Departure",
                "activities": "Journey to Ranakpur to behold 1,444 uniquely hand-carved white marble pillars inside the 15th-century Chaumukha Temple. Afternoon transfer to airport.",
                "meals": "Breakfast & Temple Prasadam Lunch",
                "stay": "Concluding Transfers"
            }
        ]
    },
    "rajasthan": {
        "title": "Royal Rajasthan Forts, Palaces & Thar Desert Caravan",
        "tagline": "A grand royal odyssey from the City of Lakes to the golden dunes of Jaisalmer and blue alleys of Jodhpur",
        "category": "Cultural & Royal Heritage",
        "season_climate": "October to March (Warm Days 24°C, Crisp Desert Nights 12°C)",
        "stay_type": "Heritage Havelis, Palace Hotels & Luxury Swiss Desert Tents",
        "transit_mode": "Private AC Force Urbania Coach & 4x4 Thar Desert Gypsies",
        "meeting_point": "08:30 AM at Jaipur International Airport / Railway Station VIP Gate",
        "dropoff_point": "06:00 PM at Jodhpur Airport / Railway Station",
        "packing_essentials": [
            "Sturdy walking shoes for steep fort ascents and desert dunes",
            "Breathable daytime linen/cotton and heavy warm fleece for desert nights",
            "Polarized sunglasses, sun scarf/turban, and broad-spectrum sunscreen",
            "Power bank, camera gear with dust protection pouch",
            "Valid government photo ID"
        ],
        "health_advisory": "Moderate walking across forts and steps. Camel safari and dune bashing involves mild motion.",
        "inclusions": [
            "All heritage palace and luxury desert camp accommodations",
            "Daily royal breakfast and curated regional dinners with live folk music",
            "All fort entries: Amber Fort, Mehrangarh, Jaisalmer Living Fort",
            "Sunset camel safari & 4x4 dune bashing across Sam Sand Dunes",
            "Certified historian guides across all heritage monuments",
            "Private air-conditioned transit for entire inter-city route",
            "All road tolls, state border taxes, and 24x7 trip concierge"
        ],
        "exclusions": [
            "Domestic/international flights to Jaipur and from Jodhpur",
            "Personal travel insurance",
            "Optional hot-air ballooning or vintage car rides",
            "Tips and personal expenses"
        ],
        "days": [
            {
                "title": "Arrival in Jaipur (The Pink City) & Twilight Amber Fort Illumination",
                "activities": "Welcome pickup and haveli check-in. Afternoon stop at Hawa Mahal facade and Albert Hall museum. Sunset excursion to Amber Fort with elephant courtyard walk and evening sound & light show.",
                "meals": "Royal Welcome Dinner",
                "stay": "Heritage Haveli, Jaipur"
            },
            {
                "title": "City Palace, Jantar Mantar & Drive to the Blue City of Jodhpur",
                "activities": "Morning tour of Maharaja's City Palace and UNESCO Jantar Mantar astronomical observatory. Scenic highway transit across the semi-arid plains to Jodhpur, checking into a boutique hotel below Mehrangarh Fort.",
                "meals": "Breakfast & Authentic Highway Lunch",
                "stay": "Heritage Hotel, Jodhpur"
            },
            {
                "title": "Mehrangarh Fort Citadel, Jaswant Thada & Blue City Stepwells",
                "activities": "Ascend the colossal ramparts of Mehrangarh Fort, exploring royal palanquins, armor, and miniature paintings. Walk to the white marble cenotaph of Jaswant Thada and descend through the azure-painted lanes of Navchokiya to Toorji Ka Jhalra stepwell.",
                "meals": "Breakfast & Rooftop Rajasthani Dinner",
                "stay": "Heritage Hotel, Jodhpur"
            },
            {
                "title": "Journey into the Thar Desert & Luxury Glamping at Sam Dunes",
                "activities": "Drive into the golden heart of Thar Desert via the sacred Kuldhara ghost village. Check into luxury Swiss desert tents. Golden hour camel caravan into the undulating dunes followed by live Kalbelia folk dance, music, and starry campfire dinner.",
                "meals": "Breakfast & Desert Camp Feast",
                "stay": "Luxury Swiss Camp, Sam Sand Dunes, Jaisalmer"
            },
            {
                "title": "Jaisalmer Living Fort, Patwon Ki Haveli & Concluding Farewell",
                "activities": "Morning exploration of the golden sandstone Sonar Qila (Jaisalmer Fort) where a quarter of the city still resides. Tour the delicate lattice carvings of Patwon Ki Haveli and Gadisar Lake before departure transfers.",
                "meals": "Breakfast & Farewell Lunch",
                "stay": "Concluding Transfers"
            }
        ]
    },
    "spiti": {
        "title": "Spiti Valley & High Himalayas 4x4 Expedition",
        "tagline": "Traverse dramatic mountain passes, ancient thousand-year-old monasteries, and camp under the Milky Way at Chandratal",
        "category": "Mountain Trek & 4x4 Expedition",
        "season_climate": "June to September (Crisp Alpine Days 18°C, Chilly Nights 3°C)",
        "stay_type": "Traditional Spitian Homestays & Alpine Lake Camps",
        "transit_mode": "Modified 4x4 Expeditions Gypsy / Scorpio with Experienced Mountain Chauffeur",
        "meeting_point": "07:00 AM at Manali Mall Road / Old Manali Bridge",
        "dropoff_point": "06:00 PM at Manali / Chandigarh",
        "packing_essentials": [
            "Layered thermal innerwear, down jacket, windproof shell",
            "High-ankle waterproof trekking boots with extra wool socks",
            "UV Category 4 sunglasses and lip protection",
            "Personal water purification bottle and hydration pack",
            "Altitude medicine (Diamox) & personal first aid"
        ],
        "health_advisory": "High altitude expedition (up to 4,590m). Strict hydration and 24-hr gradual acclimatization observed.",
        "inclusions": [
            "4x4 Expedition vehicle with fuel, permits, and mountain driver",
            "All rustic homestays and alpine glamping at Chandratal",
            "Nutritious warm mountain meals (Breakfast & Dinner)",
            "Inner Line Permits for Spiti Valley and Rohtang/Atal Tunnel",
            "Wilderness First Responder with portable oxygen cylinder"
        ],
        "exclusions": [
            "Transport to Manali starting point",
            "Personal travel/trekking insurance with evacuation coverage",
            "Personal gear and snacks"
        ],
        "days": [
            {
                "title": "Manali to Kaza via Atal Tunnel & Kunzum Pass (4,590m)",
                "activities": "Early departure crossing through Atal Tunnel into Lahaul valley. Ascend the rugged Kunzum Pass with traditional circumambulation of Kunzum Mata stupa. Descend along the Spiti river into the high-altitude capital of Kaza.",
                "meals": "Dinner",
                "stay": "Spitian Boutique Guesthouse, Kaza"
            },
            {
                "title": "Key Monastery, Kibber Village & Chicham Suspension Bridge",
                "activities": "Morning prayer ceremony at the 1,000-year-old fortified Key Gompa perched on a conical hill. Drive to Kibber wildlife sanctuary, then cross the breathtaking Chicham Bridge — the highest suspension bridge in Asia.",
                "meals": "Breakfast & Tibetan Dinner",
                "stay": "Spitian Boutique Guesthouse, Kaza"
            },
            {
                "title": "Highest Post Office at Hikkim, Komic & Langza Fossil Village",
                "activities": "Send handwritten postcards from Hikkim (world's highest post office at 4,440m). Visit Komic (highest motorable monastery village) and marvel at the giant golden Buddha overlooking snow-clad peaks at Langza. Hunt for prehistoric marine fossils.",
                "meals": "Breakfast & Homestay Dinner",
                "stay": "Traditional Eco-Homestay, Langza"
            },
            {
                "title": "Tabo 1000-Year UNESCO Gompa & Dhankar Cliff Monastery",
                "activities": "Excursion to Tabo Monastery, revered as the Ajanta of the Himalayas. Hike up to the gravity-defying Dhankar Monastery balanced on a jagged cliff edge overlooking the confluence of Spiti and Pin rivers.",
                "meals": "Breakfast & Monastic Lunch & Dinner",
                "stay": "Spitian Guesthouse, Kaza"
            },
            {
                "title": "Chandratal (The Moon Lake) Camping under Billion Stars",
                "activities": "Off-road journey across river crossings to the turquoise crescent-shaped Moon Lake (Chandratal at 4,300m). Afternoon circuit walk around the sacred lake perimeter. Stargazing beneath clear Bortle-1 night skies.",
                "meals": "Breakfast & Warm Camp Dinner",
                "stay": "Dome Tents, Chandratal Campsite"
            },
            {
                "title": "Chandratal to Manali via Batal & Rohtang Pass Descent",
                "activities": "Stop at the legendary Chacha-Chachi Dhaba at Batal for breakfast. Negotiate the rugged Gramphu boulders and descend back into the lush pine forests of Manali.",
                "meals": "Breakfast",
                "stay": "Expedition Concludes at Manali"
            }
        ]
    },
    "kashmir": {
        "title": "Paradise on Earth: Kashmir Alpine Lakes & Valley Circuit",
        "tagline": "Glide on tranquil Dal Lake shikaras, ride the highest gondola in Gulmarg, and walk amid the pine valleys of Pahalgam",
        "category": "Alpine Valley & Nature Escapes",
        "season_climate": "April to October (Pleasant 16°C – 26°C)",
        "stay_type": "Heritage Cedar Wood Houseboats & Pine Valley Alpine Resorts",
        "transit_mode": "Private AC Vehicle & Wooden Shikara",
        "meeting_point": "10:00 AM at Sheikh ul-Alam International Airport, Srinagar",
        "dropoff_point": "04:00 PM at Srinagar Airport",
        "packing_essentials": [
            "Comfortable walking shoes & warm woolen pullover / Pashmina",
            "Rain jacket or umbrella for sudden alpine showers",
            "Sunglasses & moisturizing sun cream",
            "Camera and battery packs"
        ],
        "health_advisory": "Easy to moderate walking. Gondola ride reaches 3,980m so warm layers are mandatory.",
        "inclusions": [
            "Luxury cedar wood carved houseboat stay on Dal Lake / Nigeen Lake",
            "4-Star alpine resort stays in Gulmarg and Pahalgam",
            "Daily Kashmiri breakfast and authentic multi-course Wazwan dinner",
            "Private morning and sunset shikara rides with water flower market visit",
            "Gulmarg Gondola Phase 1 & 2 tickets included",
            "Chauffeur-driven private transit with all mountain toll permits"
        ],
        "exclusions": [
            "Airfare to and from Srinagar",
            "Pony rides and private ATV rentals",
            "Personal travel insurance"
        ],
        "days": [
            {
                "title": "Arrival in Srinagar, Mughal Gardens & Sunset Dal Lake Shikara",
                "activities": "Airport pickup and traditional Kahwa welcome on a heritage wooden houseboat. Afternoon tour of terraced Mughal Gardens: Shalimar Bagh and Nishat Bagh. Sunset shikara cruise through the floating gardens and lotus channels.",
                "meals": "Traditional Wazwan Welcome Dinner",
                "stay": "Heritage Houseboat, Dal Lake, Srinagar"
            },
            {
                "title": "Gulmarg Meadow of Flowers & Apharwat Peak Gondola Ascent",
                "activities": "Scenic drive through apple orchards to Gulmarg (2,650m). Board the Gulmarg Gondola riding up to Phase 2 at Apharwat Peak (3,980m) right below snow-clad peaks. Walk through the historic St. Mary’s Church and alpine golf course.",
                "meals": "Breakfast & Alpine Dinner",
                "stay": "Resort & Spa, Gulmarg"
            },
            {
                "title": "Pahalgam Valley of Shepherds, Betaab & Aru Valleys",
                "activities": "Drive through saffron fields of Pampore to Pahalgam. Follow the turquoise Lidder river into picturesque Betaab Valley and Aru alpine biosphere. Evening walk along the pine forest trails.",
                "meals": "Breakfast & Dinner",
                "stay": "Riverside Pine Resort, Pahalgam"
            },
            {
                "title": "Old Srinagar Heritage Walk & Floating Flower Market",
                "activities": "Early morning sunrise shikara to the 100-year-old floating vegetable and flower market. Guided walk through Old Srinagar visiting Jamia Masjid and historic wooden bridges over Jhelum river.",
                "meals": "Breakfast & Farewell High Tea",
                "stay": "Heritage Houseboat / Hotel, Srinagar"
            }
        ]
    },
    "kerala": {
        "title": "God’s Own Country: Munnar Tea Mist & Backwaters Luxury Cruise",
        "tagline": "Unwind amid rolling emerald tea plantations, spice trails, and a private luxury houseboat glide through serene backwaters",
        "category": "Wellness & Coastal Backwaters",
        "season_climate": "September to March (Pleasant 20°C – 28°C)",
        "stay_type": "Plantation Colonial Bungalows & Traditional Air-Conditioned Kettuvallam Houseboats",
        "transit_mode": "Private Chauffeur AC Vehicle & Private Houseboat",
        "meeting_point": "09:30 AM at Cochin International Airport (COK)",
        "dropoff_point": "05:00 PM at Cochin International Airport",
        "packing_essentials": [
            "Breathable cotton clothes and light cardigan for Munnar hills",
            "Walking sandals and water-resistant footwear",
            "Eco-friendly insect repellent and sun hat"
        ],
        "health_advisory": "Relaxing and leisurely pace suitable for all ages.",
        "inclusions": [
            "All boutique plantation resort and private luxury houseboat stays",
            "All meals on houseboat prepared fresh by private on-board chef",
            "Daily breakfast and curated South Indian culinary experiences",
            "Tea factory tasting tour and guided cardamom spice plantation walk",
            "Kathakali dance and Kalaripayattu martial arts cultural tickets"
        ],
        "exclusions": [
            "Flights to/from Cochin",
            "Ayurvedic spa treatments outside included sessions",
            "Personal expenses"
        ],
        "days": [
            {
                "title": "Fort Kochi Colonial Heritage to Munnar Misty Hills",
                "activities": "Morning pickup in Kochi. Visit Chinese Fishing Nets and Jewish Synagogue in Mattancherry. Ascend the lush Western Ghats passing Cheeyappara Waterfalls into Munnar tea country.",
                "meals": "Dinner",
                "stay": "Plantation Estate Resort, Munnar"
            },
            {
                "title": "Eravikulam Nilgiri Tahr Sanctuary & Tea Museum Pacing",
                "activities": "Morning safari into Eravikulam National Park to spot the endangered Nilgiri Tahr mountain goat. Guided tea-plucking workshop and tasting at a 100-year-old colonial tea estate. Evening Kalaripayattu martial arts performance.",
                "meals": "Breakfast & Dinner",
                "stay": "Plantation Estate Resort, Munnar"
            },
            {
                "title": "Alleppey Backwaters Private Luxury Houseboat Cruise",
                "activities": "Descent to the tranquil palm-fringed backwaters of Alleppey. Board an exclusive private Kettuvallam houseboat. Glide through narrow canals, paddy fields below sea level, and tranquil village hamlets. Freshly caught Karimeen fish dinner cooked by private chef.",
                "meals": "Breakfast, Authentic Kerala Lunch & Dinner",
                "stay": "Private AC Luxury Houseboat, Alleppey"
            },
            {
                "title": "Marari Beach Serenity & Concluding Transfers",
                "activities": "Wake up to mist rising over the backwaters. Morning cruise to jetty, followed by a seaside brunch at Marari Beach before afternoon airport transfers.",
                "meals": "Breakfast & Coastal Brunch",
                "stay": "Concluding Transfers"
            }
        ]
    }
}


def generate_professional_itinerary(
    destination: str,
    duration_days: int = 5,
    category: str = "Cultural",
    difficulty: str = "Moderate",
    agent_name: str = "Host Guide",
    agency_name: str = "TravelVerse Expeditions"
) -> Dict[str, Any]:
    """
    Synthesizes a rich, production-grade expedition brochure & day-by-day itinerary
    based on destination parameters.
    """
    dest_clean = destination.strip()
    dest_lower = dest_clean.lower()
    days_count = max(1, min(20, int(duration_days or 5)))

    # 1. Check for exact or substring match in presets
    matched_preset = None
    for key, preset in DESTINATION_PRESETS.items():
        if key in dest_lower or dest_lower in key:
            matched_preset = preset
            break

    if matched_preset:
        base_days = matched_preset["days"]
        # Slice or repeat/extend days to match requested duration
        final_itinerary = []
        for i in range(days_count):
            if i < len(base_days):
                day_data = dict(base_days[i])
                day_data["day"] = i + 1
            else:
                day_num = i + 1
                day_data = {
                    "day": day_num,
                    "title": f"Exploration of Hidden Gems, Local Gastronomy & Countryside Trails",
                    "activities": f"Delve deeper into the authentic outskirts of {dest_clean}. Visit artisanal workshops, enjoy leisurely photography hours, and connect with indigenous culture before evening leisure.",
                    "meals": "Breakfast & Traditional Dinner",
                    "stay": base_days[-1].get("stay", f"Curated Boutique Stay, {dest_clean}")
                }
            final_itinerary.append(day_data)

        # Update last day to wrap up
        if days_count > 1:
            final_itinerary[-1]["title"] = f"Concluding Souvenirs, Farewell Brunch & Departure Transfers"
            final_itinerary[-1]["activities"] = f"Final morning leisure and souvenir gathering in {dest_clean}. Enjoy a farewell celebration with host {agent_name} before coordinated private transfers to airport / transit terminal."
            final_itinerary[-1]["stay"] = "Departure Transfers Included"

        return {
            "title": matched_preset["title"],
            "tagline": matched_preset["tagline"],
            "destination": dest_clean,
            "category": matched_preset["category"],
            "duration_days": days_count,
            "difficulty": difficulty or "Moderate",
            "season_climate": matched_preset["season_climate"],
            "stay_type": matched_preset["stay_type"],
            "transit_mode": matched_preset["transit_mode"],
            "description": (
                f"Immerse yourself in an extraordinary {days_count}-day curated expedition to {dest_clean}, "
                f"hosted with distinction by {agent_name} ({agency_name}). Designed for discerning travellers "
                f"who value deep cultural authenticity, bespoke comfort, and seamless ground logistics. "
                f"From iconic monuments to off-the-beaten-path sanctuaries, experience {dest_clean} like a true insider."
            ),
            "inclusions": matched_preset["inclusions"],
            "exclusions": matched_preset["exclusions"],
            "meeting_point": matched_preset["meeting_point"],
            "dropoff_point": matched_preset["dropoff_point"],
            "packing_essentials": matched_preset["packing_essentials"],
            "health_advisory": matched_preset["health_advisory"],
            "itinerary": final_itinerary
        }

    # 2. Generic high-end procedural generator for ANY destination in the world!
    cap_dest = dest_clean.title()
    cat_title = category.title() if category else "Discovery Expedition"

    generic_days = []
    for d in range(1, days_count + 1):
        if d == 1:
            title = f"Rendezvous, Orientation & Welcome Soirée in {cap_dest}"
            acts = (
                f"Warm welcome at the central rendezvous terminal by lead guide {agent_name}. "
                f"Private chauffeur transfer to our hand-picked boutique accommodation. Settle in and enjoy an orientation briefing "
                f"outlining route coordinates, local customs, and expedition safety protocols. Conclude day one with a celebratory welcome dinner."
            )
            meals = "Curated Welcome Dinner"
            stay = f"Selected Boutique Heritage Accommodation, {cap_dest}"
        elif d == days_count:
            title = f"Sunrise Reflection, Artisan Bazaars & Concluding Transfers"
            acts = (
                f"Begin with a relaxed panoramic breakfast overlooking {cap_dest}. Explore historic artisan alleys for authentic local keepsakes. "
                f"Commemorative group photo and farewell toast before private coordinated transfer to the departing transit terminal."
            )
            meals = "Breakfast & Farewell High Tea"
            stay = "Expedition Concludes / Coordinated Transfers"
        elif d == 2:
            title = f"Iconic Landmarks, Architectural Marvels & Guided Heritage Walk"
            acts = (
                f"In-depth morning guided expedition through the crown-jewel monuments and scenic highlights of {cap_dest}. "
                f"Skip-the-line admissions with licensed local historians. Midday pause for regional culinary tasting, followed by golden hour photography at famous viewpoints."
            )
            meals = "Breakfast & Traditional Regional Lunch"
            stay = f"Selected Boutique Heritage Accommodation, {cap_dest}"
        elif d == 3:
            title = f"Wilderness Trails, Cultural Enclaves & Scenic Countryside"
            acts = (
                f"Venture into the pristine natural landscapes and rural outskirts surrounding {cap_dest}. "
                f"Interact with indigenous artisan communities, learn about sustainable craft traditions, and witness sunset over breathtaking vistas."
            )
            meals = "Breakfast & Countryside Picnic Feast"
            stay = f"Selected Boutique Heritage Accommodation, {cap_dest}"
        else:
            title = f"Off-the-Beaten-Path Expedition & Immersive Regional Highlights (Part {d-2})"
            acts = (
                f"Exclusive behind-the-scenes access to lesser-known heritage quarters, scenic trails, and scenic viewpoints around {cap_dest}. "
                f"Flexible pacing tailored to group interests with dedicated leisure and photography time."
            )
            meals = "Breakfast & Dinner"
            stay = f"Selected Boutique Heritage Accommodation, {cap_dest}"

        generic_days.append({
            "day": d,
            "title": title,
            "activities": acts,
            "meals": meals,
            "stay": stay
        })

    return {
        "title": f"The Ultimate {cap_dest} {days_count}-Day Signature Expedition",
        "tagline": f"An extraordinary curated voyage unveiling the breathtaking landscapes, hidden heritage, and vibrant soul of {cap_dest}",
        "destination": cap_dest,
        "category": cat_title,
        "duration_days": days_count,
        "difficulty": difficulty or "Moderate",
        "season_climate": "Optimal Regional Season (Temperate & Clear Skies)",
        "stay_type": "4-Star Handpicked Boutique Stays & Scenic Eco-Resorts",
        "transit_mode": "Private Chauffeur-driven AC Vehicle Throughout",
        "meeting_point": f"09:00 AM at {cap_dest} Central Station / Airport Arrivals Gate",
        "dropoff_point": f"05:00 PM at {cap_dest} Departure Terminal",
        "description": (
            f"Step beyond the conventional tourist trail with this signature {days_count}-day expedition across {cap_dest}. "
            f"Crafted and hosted personally by {agent_name} ({agency_name}), every leg of the journey balances iconic must-see highlights "
            f"with authentic local encounters, boutique hospitality, and seamless VIP logistics."
        ),
        "inclusions": [
            f"All nights premium boutique accommodation in {cap_dest}",
            "Daily chef-prepared breakfast and signature welcome/farewell dinners",
            "All monument entry tickets, sanctuary fees, and skip-the-line passes",
            "Private air-conditioned chauffeur-driven transit throughout entire itinerary",
            "Certified bilingual lead guide and local cultural storytellers",
            "24/7 dedicated on-ground host assistance and first-aid response kit"
        ],
        "exclusions": [
            f"Long-distance airfare or rail tickets to/from {cap_dest}",
            "Comprehensive personal travel and health insurance",
            "Discretionary personal expenses, laundry, and alcoholic drinks",
            "Voluntary tips and gratuities for chauffeurs and field guides"
        ],
        "packing_essentials": [
            "Comfortable, sturdy walking or trekking shoes with good traction",
            "Versatile weather-appropriate clothing with evening warm layers",
            "High-protection UV sunglasses, sunhat, and reef-safe sunscreen",
            "Universal travel adapter, power bank, and camera gear",
            "Valid government photo identification card or passport"
        ],
        "health_advisory": (
            "Designed for travelers with an average active fitness level. Involves moderate walking across historic sites and cobblestones. "
            "Please notify your host guide of any allergies, dietary needs, or medical requirements prior to departure."
        ),
        "itinerary": generic_days
    }

