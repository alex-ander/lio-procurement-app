"""Idempotent database seeding: reference data, organizations, demo accounts.

Safe to run on every startup: it inserts only the rows that are missing, so it
never duplicates data and never touches anything users created. Run manually
with:

    python -m app.seed
"""
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.data.articles import ARTICLES
from app.data.commodity_groups import COMMODITY_GROUPS
from app.data.suppliers import SUPPLIERS
from app.db.session import SessionLocal
from app.models import (
    Article,
    CommodityGroup,
    Organization,
    OrganizationMember,
    Profile,
    Supplier,
    User,
)

logger = logging.getLogger(__name__)

# Tenants + their seeded accounts (all share DEMO_PASSWORD). "Acme Corp" is the
# development organization — the only one with all three roles. The enterprise
# tenants each have a single admin so the multi-tenant setup is tangible.
DEMO_PASSWORD = "demo1234"

# (org_name, org_slug, [(email, full_name, role), ...])
ORG_ACCOUNTS: list[tuple[str, str, list[tuple[str, str, str]]]] = [
    (
        "Acme Corp",
        "acme",
        [
            ("admin@acme.com", "Alex Admin", "admin"),
            ("buyer@acme.com", "Bea Buyer", "buyer"),
            ("requester@acme.com", "Rene Requester", "requester"),
        ],
    ),
    ("Walmart", "walmart", [("admin@walmart.com", "Walmart Admin", "admin")]),
    ("Schaeffler", "schaeffler", [("admin@schaeffler.com", "Schaeffler Admin", "admin")]),
    ("Siemens", "siemens", [("admin@siemens.com", "Siemens Admin", "admin")]),
    ("BMW", "bmw", [("admin@bmw.com", "BMW Admin", "admin")]),
]


def seed_commodity_groups(db: Session) -> int:
    """Insert commodity groups that aren't already present (keyed by id)."""
    existing = set(db.scalars(select(CommodityGroup.id)))
    new = [
        CommodityGroup(id=cg_id, category=category, name=name)
        for cg_id, category, name in COMMODITY_GROUPS
        if cg_id not in existing
    ]
    db.add_all(new)
    return len(new)


def seed_suppliers(db: Session, organization_id: uuid.UUID) -> int:
    """Insert the org's suppliers that aren't already present (keyed by name)."""
    existing = set(
        db.scalars(
            select(Supplier.name).where(Supplier.organization_id == organization_id)
        )
    )
    new = [
        Supplier(
            organization_id=organization_id,
            name=s["name"],
            description=s["description"],
            category=s["category"],
            country=s["country"],
            vat_id=s["vat_id"],
            website=s["website"],
            email=s["email"],
        )
        for s in SUPPLIERS
        if s["name"] not in existing
    ]
    db.add_all(new)
    return len(new)


def seed_articles(db: Session, organization_id: uuid.UUID) -> int:
    """Insert the org's catalog articles that aren't already present (by number).

    Each article resolves its supplier by name within the same organization;
    articles whose supplier is not seeded are skipped.
    """
    # Suppliers added earlier in this transaction are pending (the session is
    # not autoflushing), so flush before resolving their ids.
    db.flush()
    supplier_ids = {
        name: sid
        for sid, name in db.execute(
            select(Supplier.id, Supplier.name).where(
                Supplier.organization_id == organization_id
            )
        )
    }
    existing = set(
        db.scalars(
            select(Article.article_number).where(
                Article.organization_id == organization_id
            )
        )
    )
    new = []
    for a in ARTICLES:
        if a["article_number"] in existing:
            continue
        supplier_id = supplier_ids.get(a["supplier_name"])
        if supplier_id is None:
            continue
        new.append(
            Article(
                organization_id=organization_id,
                article_number=a["article_number"],
                supplier_id=supplier_id,
                description=a["description"],
                unit_price=a["unit_price"],
                currency=a["currency"],
                unit=a["unit"],
                quantity=a["quantity"],
            )
        )
    db.add_all(new)
    return len(new)


def seed_organizations_and_accounts(db: Session) -> tuple[int, int]:
    """Create the tenants and their accounts (keyed by slug / email)."""
    orgs_created = 0
    users_created = 0
    for org_name, org_slug, accounts in ORG_ACCOUNTS:
        org = db.scalar(select(Organization).where(Organization.slug == org_slug))
        if org is None:
            org = Organization(name=org_name, slug=org_slug)
            db.add(org)
            db.flush()
            orgs_created += 1
        for email, full_name, role in accounts:
            if db.scalar(select(User).where(User.email == email)) is not None:
                continue
            user = User(email=email, hashed_password=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()
            db.add(Profile(id=user.id, email=email, full_name=full_name))
            db.add(
                OrganizationMember(
                    organization_id=org.id, user_id=user.id, role=role
                )
            )
            users_created += 1
    return orgs_created, users_created


def seed(db: Session) -> dict[str, int]:
    """Seed everything. Returns counts of newly created rows per kind.

    Suppliers and articles are master data owned by the development
    organization (Acme Corp); other tenants start with an empty catalog.
    """
    orgs_created, users_created = seed_organizations_and_accounts(db)
    db.flush()
    dev_org = db.scalar(select(Organization).where(Organization.slug == "acme"))
    dev_org_id = dev_org.id if dev_org else None
    counts = {
        "commodity_groups": seed_commodity_groups(db),
        # Master data belongs to Acme; skip if that org somehow isn't seeded.
        "suppliers": seed_suppliers(db, dev_org_id) if dev_org_id else 0,
        # Articles reference suppliers by name, so this must run after suppliers.
        "articles": seed_articles(db, dev_org_id) if dev_org_id else 0,
        "organizations": orgs_created,
        "users": users_created,
    }
    db.commit()
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        counts = seed(db)
    summary = ", ".join(f"+{v} {k}" for k, v in counts.items())
    print(f"Seed complete: {summary}")


if __name__ == "__main__":
    main()
