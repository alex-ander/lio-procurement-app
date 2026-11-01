"""Generate a large, category-clean commodity taxonomy.

Writes ``backend/app/data/commodity_groups.py`` (the canonical seed data
consumed by ``app.seed``).

The taxonomy is built by combinatorial expansion within each category: a curated
base item is expanded with realistic sibling variants. Every leaf name stays
inside exactly one category.

Usage:
    python scripts/generate_commodity_groups.py [TARGET]

TARGET defaults to 2000; the vocabulary below supports roughly 2,300 before
variants are exhausted — add items/variants to go higher.
"""
import sys
from pathlib import Path

TARGET_DEFAULT = 2000

# The original 50 (ids 1-50) — kept verbatim so this file stays consistent with
# migration 0001.
ORIGINAL_50 = [
    ("General Services", "Accommodation Rentals"),
    ("General Services", "Membership Fees"),
    ("General Services", "Workplace Safety"),
    ("General Services", "Consulting"),
    ("General Services", "Financial Services"),
    ("General Services", "Fleet Management"),
    ("General Services", "Recruitment Services"),
    ("General Services", "Professional Development"),
    ("General Services", "Miscellaneous Services"),
    ("General Services", "Insurance"),
    ("Facility Management", "Electrical Engineering"),
    ("Facility Management", "Facility Management Services"),
    ("Facility Management", "Security"),
    ("Facility Management", "Renovations"),
    ("Facility Management", "Office Equipment"),
    ("Facility Management", "Energy Management"),
    ("Facility Management", "Maintenance"),
    ("Facility Management", "Cafeteria and Kitchenettes"),
    ("Facility Management", "Cleaning"),
    ("Publishing Production", "Audio and Visual Production"),
    ("Publishing Production", "Books/Videos/CDs"),
    ("Publishing Production", "Printing Costs"),
    ("Publishing Production", "Software Development for Publishing"),
    ("Publishing Production", "Material Costs"),
    ("Publishing Production", "Shipping for Production"),
    ("Publishing Production", "Digital Product Development"),
    ("Publishing Production", "Pre-production"),
    ("Publishing Production", "Post-production Costs"),
    ("Information Technology", "Hardware"),
    ("Information Technology", "IT Services"),
    ("Information Technology", "Software"),
    ("Logistics", "Courier, Express, and Postal Services"),
    ("Logistics", "Warehousing and Material Handling"),
    ("Logistics", "Transportation Logistics"),
    ("Logistics", "Delivery Services"),
    ("Marketing & Advertising", "Advertising"),
    ("Marketing & Advertising", "Outdoor Advertising"),
    ("Marketing & Advertising", "Marketing Agencies"),
    ("Marketing & Advertising", "Direct Mail"),
    ("Marketing & Advertising", "Customer Communication"),
    ("Marketing & Advertising", "Online Marketing"),
    ("Marketing & Advertising", "Events"),
    ("Marketing & Advertising", "Promotional Materials"),
    ("Production", "Warehouse and Operational Equipment"),
    ("Production", "Production Machinery"),
    ("Production", "Spare Parts"),
    ("Production", "Internal Transportation"),
    ("Production", "Production Materials"),
    ("Production", "Consumables"),
    ("Production", "Maintenance and Repairs"),
]

# Variant pools keyed by an item "kind". Chosen so a variant reads plausibly for
# that kind of item and stays inside the same category.
VARIANT_POOLS = {
    "device": ["Entry-level", "Mid-range", "Premium", "Compact", "High-performance", "Refurbished", "Leased"],
    "peripheral": ["Wired", "Wireless", "USB-C", "Bluetooth", "Ergonomic", "Compact", "Premium"],
    "service": ["Basic", "Standard", "Premium", "Managed", "On-site", "Remote", "Annual Contract"],
    "software": ["Single User", "Team (10 seats)", "Enterprise", "Cloud", "On-premise", "Annual Subscription", "Perpetual License"],
    "subscription": ["Monthly", "Annual", "Multi-year", "Per-seat", "Usage-based", "Enterprise Plan"],
    "material": ["Steel", "Stainless Steel", "Aluminium", "Plastic", "Composite", "Recycled", "Galvanized"],
    "bulk": ["Small Pack", "Standard Pack", "Bulk", "Pallet", "Container Load", "Custom Quantity"],
    "logistics": ["Domestic", "EU", "International", "Express", "Standard", "Temperature-controlled"],
    "facility": ["One-off", "Recurring", "Emergency", "Contracted", "Out-of-hours"],
    "vehicle": ["Compact", "Mid-size", "Full-size", "Electric", "Hybrid", "Leased", "Fleet"],
}

# category -> list of (kind, [base items]).  Each base item is expanded with the
# variant pool for its kind. Items are unique across the whole taxonomy so every
# leaf name maps to exactly one category.
TAXONOMY: dict[str, list[tuple[str, list[str]]]] = {
    "General Services": [
        ("service", ["Management Consulting Engagement", "Recruitment Campaign", "Financial Audit", "Legal Advisory Retainer", "Translation Project"]),
        ("subscription", ["Professional Membership", "Insurance Policy", "Training Subscription", "Advisory Retainer", "Certification Program"]),
        ("facility", ["Event Catering", "Corporate Relocation", "Document Archiving", "Notary Appointment", "Background Check"]),
    ],
    "Facility Management": [
        ("facility", ["Office Cleaning", "HVAC Servicing", "Elevator Maintenance", "Pest Control Visit", "Window Cleaning"]),
        ("service", ["Security Guarding", "Landscaping", "Waste Collection", "Fire Safety Inspection", "Painting Job"]),
        ("device", ["Access Control Reader", "CCTV Camera", "Fire Extinguisher", "Air Conditioning Unit", "Office Partition"]),
    ],
    "Publishing Production": [
        ("service", ["Copy-editing", "Proofreading", "Typesetting", "Indexing", "Localization"]),
        ("bulk", ["Offset Printing Run", "Digital Printing Run", "Hardcover Binding", "Softcover Binding", "Booklet Stapling"]),
        ("material", ["Coated Paper Stock", "Uncoated Paper Stock", "Book Cloth", "Printing Ink", "Laminating Film"]),
    ],
    "Information Technology": [
        ("device", ["Business Laptop", "Desktop Workstation", "Rack Server", "Network Switch", "Tablet Device"]),
        ("peripheral", ["Monitor", "Keyboard", "Docking Station", "Webcam", "Headset"]),
        ("software", ["Office Productivity Suite", "Antivirus License", "Database License", "BI Analytics Tool", "Backup Software"]),
    ],
    "Logistics": [
        ("logistics", ["Palletized Freight", "Parcel Shipment", "Container Shipment", "Courier Delivery", "Groupage Freight"]),
        ("service", ["Customs Clearance", "Warehousing", "Order Fulfilment", "Returns Processing", "Freight Insurance"]),
        ("vehicle", ["Delivery Van Hire", "Refrigerated Truck", "Forklift Rental", "Cargo Trailer", "Last-mile Scooter"]),
    ],
    "Marketing & Advertising": [
        ("service", ["Brand Strategy", "PR Campaign", "Media Buying", "Market Research Study", "Copywriting"]),
        ("subscription", ["Social Media Advertising", "Search Engine Marketing", "Email Marketing Platform", "Marketing Automation", "Influencer Partnership"]),
        ("bulk", ["Printed Brochures", "Roll-up Banners", "Promotional Mugs", "Branded Apparel", "Trade Show Stand"]),
    ],
    "Production": [
        ("material", ["Sheet Metal", "Injection-molded Parts", "Industrial Adhesive", "Cutting Fluid", "Raw Polymer Pellets"]),
        ("device", ["CNC Machine", "Assembly Robot", "Conveyor Belt", "Industrial Press", "Packaging Machine"]),
        ("bulk", ["Fasteners Assortment", "Spare Parts Kit", "Bearings Set", "Gaskets Pack", "Lubricant Drum"]),
    ],
    "Human Resources": [
        ("service", ["Payroll Processing", "Benefits Administration", "Executive Search", "Onboarding Program", "Outplacement Support"]),
        ("subscription", ["HRIS Platform", "Learning Management System", "Performance Review Tool", "Employee Engagement Survey", "Applicant Tracking System"]),
        ("facility", ["Corporate Wellness Session", "Team Offsite", "Diversity Workshop", "Health Screening", "First-aid Training"]),
    ],
    "Finance & Legal": [
        ("service", ["Statutory Audit", "Tax Advisory", "Debt Collection", "Contract Review", "Compliance Assessment"]),
        ("subscription", ["Payment Gateway", "Expense Management Tool", "Treasury Platform", "Credit Rating Service", "E-signature Service"]),
        ("facility", ["IP Filing", "Litigation Support", "Regulatory Filing", "Due Diligence", "Insurance Brokerage"]),
    ],
    "Travel & Expenses": [
        ("logistics", ["Economy Flight", "Business Flight", "Rail Ticket", "Airport Transfer", "Ferry Crossing"]),
        ("facility", ["Hotel Night", "Serviced Apartment", "Conference Venue", "Meeting Room Hire", "Event Space"]),
        ("vehicle", ["Airport Car Rental", "Chauffeur Service", "City Car Rental", "Van Rental", "E-scooter Pass"]),
    ],
    "Office & Administration": [
        ("bulk", ["Copy Paper", "Notebooks", "Pens Assortment", "Toner Cartridges", "Filing Folders"]),
        ("device", ["Office Desk", "Ergonomic Chair", "Meeting Table", "Storage Cabinet", "Whiteboard"]),
        ("service", ["Mailroom Service", "Document Shredding", "Reception Staffing", "Coffee Supply", "Water Cooler Service"]),
    ],
    "Research & Development": [
        ("device", ["Laboratory Centrifuge", "Microscope", "Spectrometer", "3D Printer", "Environmental Chamber"]),
        ("bulk", ["Reagents Kit", "Lab Consumables", "Sample Vials", "Petri Dishes", "Pipette Tips"]),
        ("service", ["Clinical Trial Management", "Product Testing", "Certification Testing", "Prototyping Service", "Patent Search"]),
    ],
    "Telecommunications": [
        ("subscription", ["Mobile Phone Plan", "Fixed-line Plan", "Business Internet", "VoIP Package", "SMS Gateway"]),
        ("device", ["IP Desk Phone", "Conference Speakerphone", "Mobile Handset", "Router", "SIM Card"]),
        ("service", ["Contact Center Service", "Video Conferencing", "Unified Communications", "Satellite Link", "Network Installation"]),
    ],
    "Utilities & Energy": [
        ("subscription", ["Electricity Supply", "Natural Gas Supply", "Water Supply", "District Heating", "Green Energy Tariff"]),
        ("device", ["Solar Panel Array", "EV Charging Station", "Backup Generator", "Smart Meter", "Battery Storage Unit"]),
        ("service", ["Energy Audit", "Emissions Monitoring", "Grid Connection", "Metering Service", "Load Management"]),
    ],
    "Professional Services": [
        ("service", ["Strategy Consulting", "Change Management", "Project Management Office", "Sustainability Consulting", "Design Thinking Workshop"]),
        ("service", ["Architecture Design", "Engineering Consulting", "Environmental Assessment", "Actuarial Analysis", "Feasibility Study"]),
        ("subscription", ["Consulting Retainer", "Interim Management", "Fractional Executive", "Coaching Program", "Benchmarking Service"]),
    ],
    "Raw Materials": [
        ("material", ["Structural Steel", "Aluminium Sheet", "Copper Wire", "Timber Planks", "Float Glass"]),
        ("bulk", ["Cement Bags", "Sand Aggregate", "Plastic Granulate", "Paper Pulp", "Textile Rolls"]),
        ("material", ["Rubber Sheeting", "Stainless Steel Coil", "Brass Rod", "Zinc Ingots", "Silica Sand"]),
    ],
    "Packaging": [
        ("bulk", ["Corrugated Boxes", "Shipping Labels", "Wooden Pallets", "Stretch Film", "Bubble Wrap"]),
        ("material", ["PET Bottles", "Glass Jars", "Aluminium Cans", "Kraft Paper", "Molded Pulp Trays"]),
        ("service", ["Packaging Design", "Contract Packing", "Label Printing", "Packaging Audit", "Prototype Packaging"]),
    ],
    "Health & Safety": [
        ("bulk", ["Safety Helmets", "High-visibility Vests", "Safety Gloves", "First-aid Kits", "Ear Protection"]),
        ("device", ["Eye Wash Station", "Fire Blanket", "Gas Detector", "Defibrillator", "Safety Barrier"]),
        ("service", ["Safety Training", "Ergonomic Assessment", "Risk Assessment", "Hazmat Handling", "Site Safety Audit"]),
    ],
    "Maintenance, Repair & Operations": [
        ("device", ["Industrial Pump", "Electric Motor", "Hydraulic Valve", "Air Compressor", "Gearbox"]),
        ("bulk", ["Ball Bearings", "Fasteners Set", "Air Filters", "V-belts", "Seals and O-rings"]),
        ("device", ["Cordless Drill", "Angle Grinder", "Welding Machine", "Torque Wrench", "Multimeter"]),
    ],
    "Automotive & Fleet": [
        ("vehicle", ["Company Car", "Delivery Van", "Electric Van", "Pool Car", "Pickup Truck"]),
        ("bulk", ["Tire Set", "Motor Oil", "Brake Pads", "Wiper Blades", "Vehicle Battery"]),
        ("service", ["Vehicle Servicing", "Fleet Telematics", "Fuel Card Program", "Vehicle Leasing", "Tire Fitting"]),
    ],
    "Construction & Infrastructure": [
        ("service", ["Civil Engineering Works", "Electrical Installation", "Plumbing Installation", "Demolition Works", "Site Surveying"]),
        ("material", ["Ready-mix Concrete", "Reinforcement Bar", "Insulation Panels", "Roofing Membrane", "Drywall Sheets"]),
        ("device", ["Scaffolding Set", "Excavator Hire", "Concrete Mixer", "Site Cabin", "Tower Crane Hire"]),
    ],
    "Sustainability & Environment": [
        ("service", ["Carbon Footprint Assessment", "Environmental Audit", "ESG Reporting", "Sustainability Certification", "Water Management Plan"]),
        ("subscription", ["Carbon Offset Program", "Emissions Monitoring Platform", "ESG Data Service", "Renewable Energy Certificate", "Waste Analytics"]),
        ("bulk", ["Recycling Bins", "Compost Units", "Reusable Packaging", "Energy-efficient Lighting", "Water-saving Fixtures"]),
    ],
}


def generate(target: int) -> list[tuple[int, str, str]]:
    # Flatten to (category, kind, item), preserving category order.
    families: list[tuple[str, str, str]] = []
    for category, fams in TAXONOMY.items():
        for kind, items in fams:
            for item in items:
                families.append((category, kind, item))

    result: list[tuple[str, str]] = list(ORIGINAL_50)
    seen = {name.lower() for _, name in ORIGINAL_50}

    max_depth = 1 + max(len(pool) for pool in VARIANT_POOLS.values())
    # Depth 0 emits all base items (one per family, balanced across categories),
    # then each subsequent depth adds the next sibling variant — so we grow
    # breadth-first and keep categories balanced.
    for depth in range(max_depth):
        if len(result) >= target:
            break
        for category, kind, item in families:
            if len(result) >= target:
                break
            if depth == 0:
                name = item
            else:
                pool = VARIANT_POOLS[kind]
                if depth - 1 >= len(pool):
                    continue
                name = f"{item} — {pool[depth - 1]}"
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append((category, name))

    return [(i + 1, cat, name) for i, (cat, name) in enumerate(result)]


def write_module(rows: list[tuple[int, str, str]], out_path: Path) -> None:
    lines = [
        '"""Canonical commodity group reference data (single source of truth).',
        "",
        "GENERATED by scripts/generate_commodity_groups.py — do not edit by hand.",
        "Consumed by ``app.seed``.",
        '"""',
        "",
        "COMMODITY_GROUPS: list[tuple[int, str, str]] = [",
    ]
    for cg_id, category, name in rows:
        lines.append(f"    ({cg_id}, {category!r}, {name!r}),")
    lines.append("]")
    out_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    target = int(sys.argv[1]) if len(sys.argv) > 1 else TARGET_DEFAULT
    rows = generate(target)

    # Every leaf name must belong to exactly one category.
    by_name: dict[str, set[str]] = {}
    for _, cat, name in rows:
        by_name.setdefault(name, set()).add(cat)
    ambiguous = {n: c for n, c in by_name.items() if len(c) > 1}
    assert not ambiguous, f"names spanning multiple categories: {ambiguous}"
    assert rows[:50] == [(i + 1, c, n) for i, (c, n) in enumerate(ORIGINAL_50)]

    out = Path(__file__).resolve().parent.parent / "app" / "data" / "commodity_groups.py"
    write_module(rows, out)

    categories = sorted({c for _, c, _ in rows})
    print(f"generated {len(rows)} commodity groups across {len(categories)} categories")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
