"""End-to-end smoke test exercising every endpoint over an in-memory SQLite DB.

Run with: python -m pytest tests/ -q   (or plainly: python tests/test_smoke.py)
"""
import io
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Article, CommodityGroup, RequestActivity, Supplier
from app.seed import seed

# ---------------------------------------------------------------------------
# Test database (in-memory SQLite) + commodity group seed
# ---------------------------------------------------------------------------
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


# SQLite ignores foreign keys (and their ON DELETE CASCADE) unless enabled —
# Postgres enforces them natively.
from sqlalchemy import event  # noqa: E402


@event.listens_for(engine, "connect")
def _enable_sqlite_fks(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

Base.metadata.create_all(engine)

# Seed reference data through the same code path production uses, so the test DB
# mirrors it (large commodity taxonomy + 120 suppliers with empty descriptions).
with TestingSession() as _s:
    seed(_s)


def _override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_full_user_journey():
    # --- health ---
    assert client.get("/health").json() == {"status": "ok"}

    # --- unauthenticated access is rejected ---
    assert client.get("/requests").status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.get("/commodity-groups").status_code == 401

    # --- signup ---
    r = client.post(
        "/auth/signup",
        json={"email": "Owner@Example.com", "password": "secret123", "full_name": "Olive Owner"},
    )
    assert r.status_code == 201, r.text
    owner_token = r.json()["access_token"]
    assert r.json()["user"]["email"] == "owner@example.com"  # lower-cased

    # duplicate signup -> 409
    r = client.post(
        "/auth/signup", json={"email": "owner@example.com", "password": "secret123"}
    )
    assert r.status_code == 409

    # short password -> 422
    r = client.post("/auth/signup", json={"email": "x@example.com", "password": "abc"})
    assert r.status_code == 422

    # --- signin ---
    assert (
        client.post(
            "/auth/signin", json={"email": "owner@example.com", "password": "wrong"}
        ).status_code
        == 401
    )
    r = client.post(
        "/auth/signin", json={"email": "owner@example.com", "password": "secret123"}
    )
    assert r.status_code == 200
    owner_token = r.json()["access_token"]

    # --- me ---
    r = client.get("/auth/me", headers=_auth(owner_token))
    assert r.status_code == 200
    assert r.json()["profile"]["full_name"] == "Olive Owner"

    # --- no organization yet: org-scoped endpoints -> 403 ---
    assert client.get("/requests", headers=_auth(owner_token)).status_code == 403
    assert client.get("/organizations/me", headers=_auth(owner_token)).status_code == 403

    # --- create organization ---
    r = client.post(
        "/organizations",
        json={"name": "Acme Corp", "slug": "acme-corp"},
        headers=_auth(owner_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "admin"

    # duplicate slug -> 409
    r = client.post(
        "/organizations",
        json={"name": "Acme 2", "slug": "acme-corp"},
        headers=_auth(owner_token),
    )
    assert r.status_code == 409

    # --- organizations/me ---
    r = client.get("/organizations/me", headers=_auth(owner_token))
    assert r.status_code == 200
    assert r.json()["name"] == "Acme Corp"
    assert r.json()["role"] == "admin"

    # --- commodity groups ---
    r = client.get("/commodity-groups", headers=_auth(owner_token))
    assert r.status_code == 200
    group_ids = [g["id"] for g in r.json()]
    assert 15 in group_ids and 31 in group_ids and 43 in group_ids
    assert len(group_ids) >= 300

    # --- create request (camelCase payload, as the frontend sends) ---
    payload = {
        "requestorName": "Olive Owner",
        "titleShortDescription": "Software Licenses",
        "vendorName": "Adobe Systems",
        "vatId": "12-3456789",
        "commodityGroupId": 31,
        "totalCost": 1500.0,
        "department": "IT",
        "orderLines": [
            {
                "positionDescription": "Creative Cloud",
                "unitPrice": 150.0,
                "amount": 10,
                "unit": "licenses",
                "totalPrice": 1500.0,
            }
        ],
    }
    r = client.post("/requests", json=payload, headers=_auth(owner_token))
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]
    assert r.json()["status"] == "open"
    assert r.json()["requestor_name"] == "Olive Owner"
    assert r.json()["commodity_groups"]["name"] == "Software"
    assert len(r.json()["order_lines"]) == 1
    assert r.json()["order_lines"][0]["position_description"] == "Creative Cloud"

    # unknown commodity group -> 422
    bad = dict(payload, commodityGroupId=999999)
    assert client.post("/requests", json=bad, headers=_auth(owner_token)).status_code == 422

    # --- list requests ---
    r = client.get("/requests", headers=_auth(owner_token))
    assert r.status_code == 200
    assert len(r.json()) == 1

    # --- status update logs activity ---
    r = client.patch(
        f"/requests/{request_id}/status",
        json={"status": "in_progress"},
        headers=_auth(owner_token),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"

    def _activity_actions() -> list[str]:
        with TestingSession() as s:
            rows = s.scalars(
                select(RequestActivity)
                .where(RequestActivity.request_id == uuid.UUID(request_id))
                .order_by(RequestActivity.created_at)
            ).all()
            return [a.action for a in rows]

    # created + status_changed so far
    assert _activity_actions() == ["created", "status_changed"]

    # same-status update does NOT add activity
    client.patch(
        f"/requests/{request_id}/status",
        json={"status": "in_progress"},
        headers=_auth(owner_token),
    )
    assert _activity_actions() == ["created", "status_changed"]

    # invalid status -> 422
    r = client.patch(
        f"/requests/{request_id}/status",
        json={"status": "bogus"},
        headers=_auth(owner_token),
    )
    assert r.status_code == 422

    # --- full update replaces order lines ---
    update = {
        "requestorName": "Olive Owner",
        "title": "Software Licenses (updated)",
        "vendorName": "Adobe Systems",
        "vatId": "12-3456789",
        "commodityGroupId": 15,
        "totalCost": 500.0,
        "department": "IT",
        "orderLines": [
            {
                "positionDescription": "Desk",
                "unitPrice": 250.0,
                "amount": 2,
                "unit": "pieces",
                "totalPrice": 500.0,
            },
            {
                "positionDescription": "Chair",
                "unitPrice": 0.0,
                "amount": 1.28,
                "unit": "meters",
                "totalPrice": 0.0,
            },
        ],
    }
    r = client.put(f"/requests/{request_id}", json=update, headers=_auth(owner_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Software Licenses (updated)"
    assert body["commodity_groups"]["id"] == 15
    assert [l["position_description"] for l in body["order_lines"]] == ["Desk", "Chair"]
    assert body["order_lines"][1]["amount"] == 1.28  # decimal amounts supported
    assert [l["line_order"] for l in body["order_lines"]] == [1, 2]

    # --- invites ---
    r = client.post(
        "/organizations/me/invites",
        json={"email": "member@example.com"},
        headers=_auth(owner_token),
    )
    assert r.status_code == 201, r.text
    invite_token = None
    # token isn't exposed via the API response; fetch from DB like the email link would carry it
    from app.models import OrganizationInvite

    with TestingSession() as s:
        invite = s.scalar(
            select(OrganizationInvite).where(OrganizationInvite.email == "member@example.com")
        )
        assert invite is not None and invite.token and invite.expires_at is not None
        invite_token = invite.token

    # duplicate invite -> 409
    r = client.post(
        "/organizations/me/invites",
        json={"email": "member@example.com"},
        headers=_auth(owner_token),
    )
    assert r.status_code == 409

    # members endpoint shows 1 member + 1 pending invite
    r = client.get("/organizations/me/members", headers=_auth(owner_token))
    assert r.status_code == 200
    assert len(r.json()["members"]) == 1
    assert r.json()["members"][0]["profiles"]["full_name"] == "Olive Owner"
    assert len(r.json()["invites"]) == 1

    # --- second user accepts invite ---
    r = client.post(
        "/auth/signup",
        json={"email": "member@example.com", "password": "secret123", "full_name": "Mia Member"},
    )
    member_token = r.json()["access_token"]

    # wrong-email user cannot accept
    r = client.post(
        "/auth/signup", json={"email": "other@example.com", "password": "secret123"}
    )
    other_token = r.json()["access_token"]
    r = client.post(
        "/organizations/invites/accept",
        json={"token": invite_token},
        headers=_auth(other_token),
    )
    assert r.status_code == 403

    r = client.post(
        "/organizations/invites/accept",
        json={"token": invite_token},
        headers=_auth(member_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "requester"

    # accepted invite cannot be reused
    r = client.post(
        "/organizations/invites/accept",
        json={"token": invite_token},
        headers=_auth(member_token),
    )
    assert r.status_code == 404

    # member sees the org's requests
    r = client.get("/requests", headers=_auth(member_token))
    assert r.status_code == 200
    assert len(r.json()) == 1

    # members endpoint now shows 2 members, 0 pending invites
    r = client.get("/organizations/me/members", headers=_auth(owner_token))
    assert len(r.json()["members"]) == 2
    assert len(r.json()["invites"]) == 0

    # plain member cannot invite (admin required)
    r = client.post(
        "/organizations/me/invites",
        json={"email": "third@example.com"},
        headers=_auth(member_token),
    )
    assert r.status_code == 403

    # --- cancel invite ---
    r = client.post(
        "/organizations/me/invites",
        json={"email": "third@example.com"},
        headers=_auth(owner_token),
    )
    invite_id = r.json()["id"]
    r = client.delete(
        f"/organizations/me/invites/{invite_id}", headers=_auth(owner_token)
    )
    assert r.status_code == 204

    # --- isolation: user in a different org sees nothing ---
    r = client.post(
        "/organizations",
        json={"name": "Other Org", "slug": "other-org"},
        headers=_auth(other_token),
    )
    assert r.status_code == 201
    r = client.get("/requests", headers=_auth(other_token))
    assert r.json() == []
    # ...and cannot touch the first org's request
    assert (
        client.delete(f"/requests/{request_id}", headers=_auth(other_token)).status_code
        == 404
    )

    # --- delete request ---
    r = client.delete(f"/requests/{request_id}", headers=_auth(owner_token))
    assert r.status_code == 204
    assert client.get("/requests", headers=_auth(owner_token)).json() == []
    # order lines + activity cascaded
    with TestingSession() as s:
        assert (
            s.scalars(
                select(RequestActivity).where(
                    RequestActivity.request_id == uuid.UUID(request_id)
                )
            ).all()
            == []
        )


def test_pdf_parse():
    # Build a tiny real PDF in memory, then round-trip it through the endpoint.
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)

    r = client.post("/auth/signup", json={"email": "pdf@example.com", "password": "secret123"})
    token = r.json()["access_token"]

    r = client.post(
        "/pdf/parse",
        files={"file": ("offer.pdf", buf.getvalue(), "application/pdf")},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    assert "text" in r.json()  # blank page -> empty text, but parses fine

    # non-PDF rejected
    r = client.post(
        "/pdf/parse",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=_auth(token),
    )
    assert r.status_code == 400


def test_activity_log_and_document():
    from pypdf import PdfWriter

    admin = client.post(
        "/auth/signin", json={"email": "admin@acme.com", "password": "demo1234"}
    ).json()["access_token"]

    payload = {
        "requestorName": "Alex Admin", "titleShortDescription": "Chairs",
        "vendorName": "FurnitureCo", "vatId": "12-0000001", "commodityGroupId": 15,
        "totalCost": 500.0, "department": "Ops",
        "orderLines": [
            {"positionDescription": "Chair", "unitPrice": 250, "amount": 2, "unit": "pc", "totalPrice": 500}
        ],
    }
    rid = client.post("/requests", json=payload, headers=_auth(admin)).json()["id"]

    # edit two fields -> one 'updated' activity naming those fields
    updated = dict(payload)
    updated["title"] = "Office Chairs"
    updated["totalCost"] = 600.0
    updated["orderLines"] = [
        {"positionDescription": "Chair", "unitPrice": 300, "amount": 2, "unit": "pc", "totalPrice": 600}
    ]
    # RequestUpdate uses "title" (not titleShortDescription)
    updated = {
        "requestorName": "Alex Admin", "title": "Office Chairs", "vendorName": "FurnitureCo",
        "vatId": "12-0000001", "commodityGroupId": 15, "totalCost": 600.0, "department": "Ops",
        "orderLines": updated["orderLines"],
    }
    r = client.put(f"/requests/{rid}", json=updated, headers=_auth(admin))
    assert r.status_code == 200, r.text

    # approve, then a status change
    client.patch(f"/requests/{rid}/approval", json={"decision": "approved"}, headers=_auth(admin))
    client.patch(f"/requests/{rid}/status", json={"status": "closed"}, headers=_auth(admin))

    # attach a PDF
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    r = client.put(
        f"/requests/{rid}/document",
        files={"file": ("offer.pdf", buf.getvalue(), "application/pdf")},
        headers=_auth(admin),
    )
    assert r.status_code == 204, r.text

    # activity feed (newest first) captures every event
    r = client.get(f"/requests/{rid}/activity", headers=_auth(admin))
    assert r.status_code == 200
    actions = [a["action"] for a in r.json()]
    assert set(actions) == {
        "created", "updated", "approved", "status_changed", "document_attached"
    }
    updated_entry = next(a for a in r.json() if a["action"] == "updated")
    assert set(updated_entry["detail"]["changed_fields"]) == {
        "title", "total_cost", "order_lines"
    }

    # the stored PDF is served back
    r = client.get(f"/requests/{rid}/document", headers=_auth(admin))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"

    client.delete(f"/requests/{rid}", headers=_auth(admin))


def test_extraction_without_api_key():
    from app.core.config import settings

    r = client.post("/auth/signup", json={"email": "ex@example.com", "password": "secret123"})
    token = r.json()["access_token"]

    prev_key = settings.openai_api_key
    settings.openai_api_key = None
    try:
        r = client.post("/extraction", json={"text": "Quote No. 123"}, headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        # Without OPENAI_API_KEY configured the endpoint reports a clean failure
        # envelope rather than an HTTP error.
        assert body["success"] is False
        assert "OPENAI_API_KEY" in body["error"]

        # empty text
        r = client.post("/extraction", json={"text": "  "}, headers=_auth(token))
        assert r.json()["success"] is False
    finally:
        settings.openai_api_key = prev_key


def test_commodity_groups_expanded():
    r = client.post("/auth/signup", json={"email": "cg@example.com", "password": "secret123"})
    token = r.json()["access_token"]

    r = client.get("/commodity-groups", headers=_auth(token))
    assert r.status_code == 200
    groups = r.json()
    # Large taxonomy.
    assert len(groups) >= 1000, f"expected a large taxonomy, got {len(groups)}"
    # ids contiguous from 1; first one matches the original taxonomy
    assert groups[0] == {"id": 1, "category": "General Services", "name": "Accommodation Rentals"}
    assert len({g["category"] for g in groups}) >= 20

    # Every leaf name belongs to exactly one category.
    by_name: dict[str, set[str]] = {}
    for g in groups:
        by_name.setdefault(g["name"], set()).add(g["category"])
    ambiguous = {n: c for n, c in by_name.items() if len(c) > 1}
    assert not ambiguous, f"names spanning multiple categories: {ambiguous}"


def _signin(email: str, password: str = "demo1234") -> str:
    r = client.post("/auth/signin", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_suppliers_are_org_scoped_master_data():
    token = _signin("admin@acme.com")

    # auth required
    assert client.get("/suppliers").status_code == 401

    r = client.get("/suppliers/count", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["count"] >= 100

    r = client.get("/suppliers?limit=500", headers=_auth(token))
    assert r.status_code == 200
    suppliers = r.json()
    assert len(suppliers) >= 100
    # every seeded supplier has an empty description, ready for enrichment
    assert all((s["description"] or "") == "" for s in suppliers)
    # sorted by name, carries catalog metadata
    assert suppliers == sorted(suppliers, key=lambda s: s["name"])
    assert all(s["name"] and s["category"] for s in suppliers)

    # search filter works
    r = client.get("/suppliers?search=freight", headers=_auth(token))
    assert r.status_code == 200
    assert len(r.json()) >= 1
    assert all("freight" in s["name"].lower() for s in r.json())

    # master data is private to Acme: another tenant sees none of it
    other = _signin("admin@walmart.com")
    assert client.get("/suppliers/count", headers=_auth(other)).json()["count"] == 0
    assert client.get("/suppliers?limit=500", headers=_auth(other)).json() == []


def test_articles_catalog_paginated_and_searchable():
    token = _signin("admin@acme.com")

    # auth required
    assert client.get("/articles").status_code == 401

    r = client.get("/articles/count", headers=_auth(token))
    assert r.status_code == 200
    total = r.json()["count"]
    assert total >= 1000

    # first page: bounded size, correct envelope, ordered by article number
    r = client.get("/articles?limit=25&offset=0", headers=_auth(token))
    assert r.status_code == 200
    page = r.json()
    assert page["total"] == total
    assert page["limit"] == 25 and page["offset"] == 0
    assert len(page["items"]) == 25
    numbers = [a["article_number"] for a in page["items"]]
    assert numbers == sorted(numbers)
    # every article carries its supplier and a price
    assert all(a["supplier_id"] and a["supplier_name"] for a in page["items"])
    assert all(a["description"] and a["unit"] for a in page["items"])

    # second page returns different rows
    r2 = client.get("/articles?limit=25&offset=25", headers=_auth(token))
    assert r2.status_code == 200
    assert {a["id"] for a in r2.json()["items"]}.isdisjoint({a["id"] for a in page["items"]})

    # search matches the seeded office-decoration items
    r = client.get("/articles?search=moss", headers=_auth(token))
    assert r.status_code == 200
    found = r.json()
    assert found["total"] >= 1
    assert any("moss wall" in a["description"].lower() for a in found["items"])

    # catalog is private to Acme: another tenant's catalog is empty
    other = _signin("admin@walmart.com")
    assert client.get("/articles/count", headers=_auth(other)).json()["count"] == 0
    assert client.get("/articles", headers=_auth(other)).json()["total"] == 0


def test_seed_is_idempotent():
    # The DB was already seeded at import; seeding again must add nothing and
    # must not change the row counts (safe to run on every startup).
    with TestingSession() as db:
        before_cg = db.scalar(select(func.count()).select_from(CommodityGroup))
        before_sup = db.scalar(select(func.count()).select_from(Supplier))
        before_art = db.scalar(select(func.count()).select_from(Article))
        counts = seed(db)
        after_cg = db.scalar(select(func.count()).select_from(CommodityGroup))
        after_sup = db.scalar(select(func.count()).select_from(Supplier))
        after_art = db.scalar(select(func.count()).select_from(Article))

    assert all(v == 0 for v in counts.values()), counts
    assert before_cg == after_cg
    assert before_sup == after_sup
    assert before_art == after_art


def test_demo_user_can_sign_in():
    # The seeded demo account works out of the box (documented in the README).
    r = client.post(
        "/auth/signin", json={"email": "admin@acme.com", "password": "demo1234"}
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]

    # ...and already belongs to an organization, so the app is usable immediately.
    r = client.get("/organizations/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["slug"] == "acme"
    assert r.json()["role"] == "admin"

    assert client.get("/requests", headers=_auth(token)).status_code == 200


def test_approval_flow_with_roles():
    # Uses the seeded demo org: requester creates, buyer approves.
    def signin(email: str) -> str:
        r = client.post("/auth/signin", json={"email": email, "password": "demo1234"})
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    requester = signin("requester@acme.com")
    buyer = signin("buyer@acme.com")
    admin = signin("admin@acme.com")

    payload = {
        "requestorName": "Rene Requester",
        "titleShortDescription": "Laptops",
        "vendorName": "TechSupply",
        "vatId": "99-9999999",
        "commodityGroupId": 31,
        "totalCost": 4200.0,
        "department": "Engineering",
        "orderLines": [
            {"positionDescription": "Laptop", "unitPrice": 1400, "amount": 3, "unit": "pc", "totalPrice": 4200}
        ],
    }
    r = client.post("/requests", json=payload, headers=_auth(requester))
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]
    # every new request starts pending
    assert r.json()["approval_status"] == "pending"
    assert r.json()["approved_by"] is None

    # requester cannot approve (not a buyer/admin)
    r = client.patch(
        f"/requests/{request_id}/approval",
        json={"decision": "approved"},
        headers=_auth(requester),
    )
    assert r.status_code == 403

    # buyer approves
    r = client.patch(
        f"/requests/{request_id}/approval",
        json={"decision": "approved"},
        headers=_auth(buyer),
    )
    assert r.status_code == 200, r.text
    assert r.json()["approval_status"] == "approved"
    assert r.json()["approved_by"] is not None
    assert r.json()["approved_at"] is not None

    # already decided -> 409 (even for an admin)
    r = client.patch(
        f"/requests/{request_id}/approval",
        json={"decision": "rejected"},
        headers=_auth(admin),
    )
    assert r.status_code == 409

    # admins can also decide; rejection works
    r = client.post("/requests", json=payload, headers=_auth(requester))
    second_id = r.json()["id"]
    r = client.patch(
        f"/requests/{second_id}/approval",
        json={"decision": "rejected"},
        headers=_auth(admin),
    )
    assert r.status_code == 200
    assert r.json()["approval_status"] == "rejected"

    # buyers cannot touch org settings (admin-only)
    assert (
        client.patch(
            "/organizations/me/settings",
            json={"required_fields": []},
            headers=_auth(buyer),
        ).status_code
        == 403
    )

    # cleanup: remove the demo-org requests this test created
    for rid in (request_id, second_id):
        client.delete(f"/requests/{rid}", headers=_auth(admin))


def test_org_settings_required_fields():
    # Fresh org (settings default to empty).
    r = client.post(
        "/auth/signup", json={"email": "settings@example.com", "password": "secret123"}
    )
    token = r.json()["access_token"]
    client.post(
        "/organizations",
        json={"name": "Settings Co", "slug": "settings-co"},
        headers=_auth(token),
    )

    # Default settings: nothing extra required.
    r = client.get("/organizations/me/settings", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {"required_fields": []}

    base_payload = {
        "requestorName": "S", "titleShortDescription": "T", "vendorName": "V",
        "vatId": "", "commodityGroupId": 31, "totalCost": 10.0, "department": "",
        "orderLines": [
            {"positionDescription": "x", "unitPrice": 10, "amount": 1, "unit": "pc", "totalPrice": 10}
        ],
    }
    # Without a requirement, a request with blank vat_id/department is accepted.
    assert client.post("/requests", json=base_payload, headers=_auth(token)).status_code == 201

    # Configure vat_id + department as required.
    r = client.patch(
        "/organizations/me/settings",
        json={"required_fields": ["vat_id", "department"]},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert set(r.json()["required_fields"]) == {"vat_id", "department"}

    # Now the same blank-field request is rejected...
    r = client.post("/requests", json=base_payload, headers=_auth(token))
    assert r.status_code == 422
    assert "vat_id" in r.json()["detail"] and "department" in r.json()["detail"]

    # ...and providing them succeeds.
    ok = dict(base_payload, vatId="12-3000123", department="IT")
    assert client.post("/requests", json=ok, headers=_auth(token)).status_code == 201

    # Unknown setting keys are rejected (validated at the edge).
    assert (
        client.patch(
            "/organizations/me/settings",
            json={"bogus": True},
            headers=_auth(token),
        ).status_code
        == 422
    )


def test_org_settings_admin_only():
    # A plain member cannot change settings.
    owner = client.post(
        "/auth/signup", json={"email": "so-owner@example.com", "password": "secret123"}
    ).json()["access_token"]
    client.post(
        "/organizations",
        json={"name": "SO Co", "slug": "so-co"},
        headers=_auth(owner),
    )
    invite = client.post(
        "/organizations/me/invites",
        json={"email": "so-member@example.com"},
        headers=_auth(owner),
    )
    from app.models import OrganizationInvite

    with TestingSession() as db:
        token_val = db.scalar(
            select(OrganizationInvite.token).where(
                OrganizationInvite.email == "so-member@example.com"
            )
        )
    member = client.post(
        "/auth/signup", json={"email": "so-member@example.com", "password": "secret123"}
    ).json()["access_token"]
    client.post(
        "/organizations/invites/accept", json={"token": token_val}, headers=_auth(member)
    )

    # member can read settings but not change them
    assert client.get("/organizations/me/settings", headers=_auth(member)).status_code == 200
    r = client.patch(
        "/organizations/me/settings",
        json={"required_fields": ["vat_id"]},
        headers=_auth(member),
    )
    assert r.status_code == 403


def test_catalog_article_suggestions_and_negotiated_pricing():
    requester = _signin("requester@acme.com")
    admin = _signin("admin@acme.com")
    walmart = _signin("admin@walmart.com")

    # 1. Multi-token search on GET /articles works when words aren't contiguous
    r = client.get("/articles?search=preserved+moss+wall", headers=_auth(requester))
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    assert any(a["article_number"] == "HAR-00172" for a in r.json()["items"])

    # 2. GET /articles/suggest matches quote-style descriptions and calculates savings
    r = client.get(
        "/articles/suggest",
        params={
            "q": 'Module "Forest & Ball Moss"',
            "unit": "square feet",
            "amount": 13.78,
            "total_price": 716.56,
            "title": "Moss Wall Installation",
        },
        headers=_auth(requester),
    )
    assert r.status_code == 200, r.text
    suggestions = r.json()
    assert len(suggestions) >= 1
    top = suggestions[0]
    assert top["article"]["article_number"] == "HAR-00172"
    assert float(top["article"]["unit_price"]) == 44.59
    assert top["unitMatches"] is True
    assert abs(top["estimatedTotalPrice"] - 614.45) <= 0.02
    assert abs(top["savings"] - 102.11) <= 0.02

    # 3. POST /articles/match batch-matches multiple order lines
    match_payload = {
        "title": "Moss Wall & Laptops",
        "vendorName": "Greenmantle Moss Studio, LLC",
        "orderLines": [
            {
                "positionDescription": 'Moss Art Panel "Mixed Moss" 63 x 24 in',
                "unitPrice": 715.26,
                "amount": 1.0,
                "unit": "pieces",
                "totalPrice": 715.26,
            },
            {
                "positionDescription": "13-inch MacBook Air: Apple M2 chip, 16GB, 512GB SSD",
                "unitPrice": 1409.06,
                "amount": 1.0,
                "unit": "pieces",
                "totalPrice": 1409.06,
            },
        ],
        "limitPerLine": 3,
    }
    r = client.post("/articles/match", json=match_payload, headers=_auth(requester))
    assert r.status_code == 200, r.text
    matched_lines = r.json()["lines"]
    assert len(matched_lines) == 2
    moss_nums = [s["article"]["article_number"] for s in matched_lines[0]["suggestions"]]
    assert "RED-00196" in moss_nums or "HAR-00172" in moss_nums
    laptop_descs = [s["article"]["description"] for s in matched_lines[1]["suggestions"]]
    assert any("business laptop" in d.lower() for d in laptop_descs)

    # Tenant isolation: Walmart has an empty catalog, so suggestions are empty
    r_walmart = client.post("/articles/match", json=match_payload, headers=_auth(walmart))
    assert r_walmart.status_code == 200
    assert all(line["suggestions"] == [] for line in r_walmart.json()["lines"])

    # 4. Creating an off-catalog request surfaces suggested_articles on order_lines
    req_payload = {
        "requestorName": "Rene Requester",
        "titleShortDescription": "Moss Wall Decor",
        "vendorName": "Greenmantle Moss Studio, LLC",
        "vatId": "85-3252405",
        "commodityGroupId": 15,
        "totalCost": 715.26,
        "department": "Facilities",
        "orderLines": [
            {
                "positionDescription": 'Moss Art Panel "Mixed Moss" 63 x 24 in',
                "unitPrice": 715.26,
                "amount": 1.0,
                "unit": "pieces",
                "totalPrice": 715.26,
            }
        ],
    }
    r = client.post("/requests", json=req_payload, headers=_auth(requester))
    assert r.status_code == 201, r.text
    created = r.json()
    req_id = created["id"]
    line_id = created["order_lines"][0]["id"]
    assert created["order_lines"][0]["article_id"] is None
    line_suggestions = created["order_lines"][0]["suggested_articles"]
    assert len(line_suggestions) >= 1
    red_suggestion = next(
        s for s in line_suggestions if s["article"]["article_number"] == "RED-00196"
    )
    red_article_id = red_suggestion["article"]["id"]

    # 5. Apply the suggested catalog article to the existing order line
    r = client.post(
        f"/requests/{req_id}/order-lines/{line_id}/apply-article",
        json={"articleId": red_article_id, "updateVendor": True},
        headers=_auth(requester),
    )
    assert r.status_code == 200, r.text
    applied = r.json()
    assert applied["vendor_name"] == "Redwood Facility Group"
    assert applied["vat_id"] == "10-0009732"
    assert applied["total_cost"] == 320.0
    updated_line = applied["order_lines"][0]
    assert updated_line["article_id"] == red_article_id
    assert updated_line["article"]["article_number"] == "RED-00196"
    assert updated_line["unit_price"] == 320.0
    assert updated_line["total_price"] == 320.0

    # Activity log recorded catalog_article_applied with savings
    r_act = client.get(f"/requests/{req_id}/activity", headers=_auth(requester))
    assert r_act.status_code == 200
    act_entry = next(
        a for a in r_act.json() if a["action"] == "catalog_article_applied"
    )
    assert act_entry["detail"]["article_number"] == "RED-00196"
    assert abs(act_entry["detail"]["savings"] - 395.26) <= 0.02

    # 6. Creating a request with articleId directly enforces the negotiated catalog price
    direct_payload = {
        "requestorName": "Rene Requester",
        "titleShortDescription": "Framed Moss Panel",
        "vendorName": "Redwood Facility Group",
        "vatId": "10-0009732",
        "commodityGroupId": 15,
        "totalCost": 999.0,  # inflated quote total; should be adjusted down to negotiated price
        "department": "Facilities",
        "orderLines": [
            {
                "positionDescription": "Custom Moss Panel",
                "unitPrice": 499.50,  # inflated unit price; should snap to $320.00
                "amount": 2.0,
                "unit": "piece",
                "totalPrice": 999.0,
                "articleId": red_article_id,
            }
        ],
    }
    r = client.post("/requests", json=direct_payload, headers=_auth(requester))
    assert r.status_code == 201, r.text
    direct_req = r.json()
    direct_id = direct_req["id"]
    assert direct_req["order_lines"][0]["article_id"] == red_article_id
    assert direct_req["order_lines"][0]["unit_price"] == 320.0
    assert direct_req["order_lines"][0]["total_price"] == 640.0
    assert direct_req["total_cost"] == 640.0

    # Unknown or cross-tenant articleId is rejected with 422
    bad_payload = dict(direct_payload)
    bad_payload["orderLines"] = [
        dict(direct_payload["orderLines"][0], articleId=str(uuid.uuid4()))
    ]
    assert (
        client.post("/requests", json=bad_payload, headers=_auth(requester)).status_code
        == 422
    )
    assert (
        client.post("/requests", json=direct_payload, headers=_auth(walmart)).status_code
        == 422
    )

    # Cleanup
    for rid in (req_id, direct_id):
        client.delete(f"/requests/{rid}", headers=_auth(admin))


def test_extraction_attaches_catalog_suggestions(monkeypatch):
    import json
    from types import SimpleNamespace
    from app.core.config import settings
    import app.services.extraction as extraction_mod

    token = _signin("requester@acme.com")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    fake_llm_json = json.dumps(
        {
            "title": "Moss Wall Decor",
            "vendorName": "Greenmantle Moss Studio, LLC",
            "vatId": "85-3252405",
            "department": "Lio Technologies",
            "orderLines": [
                {
                    "positionDescription": 'Module "Forest & Ball Moss"',
                    "unitPrice": 52.0,
                    "amount": 13.78,
                    "unit": "square feet",
                    "totalPrice": 716.56,
                }
            ],
            "totalCost": 716.56,
            "commodityGroupId": 15,
            "commodityGroupName": "Office Equipment",
        }
    )

    class _FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kw: SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content=fake_llm_json)
                            )
                        ]
                    )
                )
            )

    monkeypatch.setattr(extraction_mod, "OpenAI", _FakeOpenAI)

    r = client.post(
        "/extraction",
        json={"text": "Sample quote text for Forest & Ball Moss wall"},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    lines = body["data"]["orderLines"]
    assert len(lines) == 1
    assert len(lines[0]["suggestedArticles"]) >= 1
    top_suggestion = lines[0]["suggestedArticles"][0]
    assert top_suggestion["article"]["article_number"] == "HAR-00172"
    assert float(top_suggestion["article"]["unit_price"]) == 44.59
    assert abs(top_suggestion["savings"] - 102.11) <= 0.02


def test_two_step_commodity_group_classification_uses_full_list(monkeypatch):
    import json
    from types import SimpleNamespace
    from app.core.config import settings
    import app.services.extraction as extraction_mod

    token = _signin("requester@acme.com")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    captured_prompts: list[str] = []

    step1_json = json.dumps(
        {
            "title": "Refurbished Business Laptops",
            "vendorName": "Hudson Systems Inc.",
            "vatId": "12-3456789",
            "department": "IT Department",
            "orderLines": [
                {
                    "positionDescription": "Refurbished 14-inch Business Laptop",
                    "unitPrice": 890.0,
                    "amount": 5.0,
                    "unit": "pieces",
                    "totalPrice": 4450.0,
                }
            ],
            "totalCost": 4450.0,
            "candidateCategories": ["Information Technology"],
        }
    )
    # 1746 = ('Information Technology', 'Business Laptop — High-performance') in the full 2,000 list
    step2_json = json.dumps(
        {
            "commodityGroupId": 1746,
            "commodityGroupName": "Business Laptop — High-performance",
        }
    )

    def _fake_create(**kwargs):
        user_msg = kwargs["messages"][1]["content"]
        captured_prompts.append(user_msg)
        reply = step1_json if len(captured_prompts) == 1 else step2_json
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))]
        )

    class _FakeTwoStepOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=_fake_create)
            )

    monkeypatch.setattr(extraction_mod, "OpenAI", _FakeTwoStepOpenAI)

    r = client.post(
        "/extraction",
        json={"text": "Quote for 5x High-performance Business Laptops"},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert len(captured_prompts) == 2

    # Step 1 prompt includes all 22 main categories and their base item families
    assert "Information Technology:" in captured_prompts[0]
    assert "Sustainability & Environment:" in captured_prompts[0]
    assert "Business Laptop — High-performance" not in captured_prompts[0]

    # Step 2 prompt includes the full sub-item list for Information Technology (including IDs > 50 and > 380)
    assert "29 | Information Technology | Hardware" in captured_prompts[1]
    assert "96 | Information Technology | Business Laptop" in captured_prompts[1]
    assert "1746 | Information Technology | Business Laptop — High-performance" in captured_prompts[1]
    assert "1 | General Services | Accommodation Rentals" not in captured_prompts[1]
    assert "11 | Facility Management | Electrical Engineering" not in captured_prompts[1]

    # Final response resolves the exact sub-item from the full 2,000-row list
    assert body["data"]["commodityGroupId"] == 1746
    assert body["data"]["commodityGroupName"] == "Business Laptop — High-performance"


def test_org_accounting_precedents_and_guidelines_in_two_step_classification(monkeypatch):
    import json
    from types import SimpleNamespace
    from app.core.config import settings
    import app.services.extraction as extraction_mod

    admin_token = _signin("admin@acme.com")
    requester_token = _signin("requester@acme.com")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    # 1. Create and correct a past request for Cable Ties -> 11 (Electrical Engineering)
    created_req = client.post(
        "/requests",
        json={
            "requestorName": "Rene Requester",
            "titleShortDescription": "Nylon Cable Ties",
            "vendorName": "Northstar Industries LP",
            "vatId": "10-0004055",
            "commodityGroupId": 151,  # initially Fasteners Assortment
            "totalCost": 45.0,
            "department": "Facilities",
            "orderLines": [
                {
                    "positionDescription": "Nylon cable ties 200mm black, 100-pack",
                    "unitPrice": 9.0,
                    "amount": 5.0,
                    "unit": "packs",
                    "totalPrice": 45.0,
                }
            ],
        },
        headers=_auth(requester_token),
    ).json()
    req_id = created_req["id"]

    # User updates/corrects the commodity group to 11 (Electrical Engineering)
    r_upd = client.put(
        f"/requests/{req_id}",
        json={
            "requestorName": "Rene Requester",
            "title": "Nylon Cable Ties",
            "vendorName": "Northstar Industries LP",
            "vatId": "10-0004055",
            "commodityGroupId": 11,
            "totalCost": 45.0,
            "department": "Facilities",
            "orderLines": [
                {
                    "positionDescription": "Nylon cable ties 200mm black, 100-pack",
                    "unitPrice": 9.0,
                    "amount": 5.0,
                    "unit": "packs",
                    "totalPrice": 45.0,
                }
            ],
        },
        headers=_auth(requester_token),
    )
    assert r_upd.status_code == 200, r_upd.text

    # 2. Configure organization accounting guidelines in Settings
    guidelines_text = (
        "For us, cable ties always have to be booked under Electrical Engineering, "
        "printer toner under IT Hardware, and small software subscriptions under Office Supplies."
    )
    r_set = client.patch(
        "/organizations/me/settings",
        json={
            "required_fields": [],
            "accounting_guidelines": guidelines_text,
            "commodity_rules": [
                {"pattern": "Printer toner", "commodity_group_id": 29},
            ],
        },
        headers=_auth(admin_token),
    )
    assert r_set.status_code == 200, r_set.text
    assert r_set.json()["accounting_guidelines"] == guidelines_text
    assert r_set.json()["commodity_rules"][0]["commodity_group_name"] == "Hardware"

    captured_prompts: list[str] = []
    # Even if Step 1 only returned "Office & Administration" for a toner quote,
    # priority_group_ids ensures 11 (Electrical Engineering), 15 (Office Equipment),
    # and 29 (Hardware) are included in Step 2's candidate list.
    step1_json = json.dumps(
        {
            "title": "LaserJet Toner Cartridges",
            "vendorName": "Lakeview Supply LP",
            "vatId": "10-0042983",
            "department": "IT",
            "orderLines": [
                {
                    "positionDescription": "Toner cartridge black, high-yield",
                    "unitPrice": 186.0,
                    "amount": 2.0,
                    "unit": "pieces",
                    "totalPrice": 372.0,
                }
            ],
            "totalCost": 372.0,
            "candidateCategories": ["Office & Administration"],
        }
    )
    step2_json = json.dumps(
        {
            "commodityGroupId": 29,
            "commodityGroupName": "Hardware",
        }
    )

    def _fake_create(**kwargs):
        user_msg = kwargs["messages"][1]["content"]
        captured_prompts.append(user_msg)
        reply = step1_json if len(captured_prompts) == 1 else step2_json
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))]
        )

    class _FakeAccountingOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=_fake_create)
            )

    monkeypatch.setattr(extraction_mod, "OpenAI", _FakeAccountingOpenAI)

    try:
        r_ext = client.post(
            "/extraction",
            json={"text": "Quote for 2x Toner cartridge black, high-yield"},
            headers=_auth(requester_token),
        )
        assert r_ext.status_code == 200, r_ext.text
        ext_body = r_ext.json()
        assert ext_body["success"] is True
        assert len(captured_prompts) == 2

        # Both Step 1 and Step 2 receive the learned user-corrected precedent and org accounting rules
        for prompt in captured_prompts:
            assert "User-Corrected Accounting Precedent" in prompt
            assert "Nylon cable ties 200mm black" in prompt
            assert "11 | Facility Management | Electrical Engineering" in prompt
            assert '"Office Supplies" corresponds to 15 | Facility Management | Office Equipment' in prompt
            assert '"IT Hardware" corresponds to 29 | Information Technology | Hardware' in prompt

        # Step 2 candidate list includes priority groups 11, 15, and 29 even though Step 1 only returned "Office & Administration"
        assert "11 | Facility Management | Electrical Engineering" in captured_prompts[1]
        assert "15 | Facility Management | Office Equipment" in captured_prompts[1]
        assert "29 | Information Technology | Hardware" in captured_prompts[1]
        assert ext_body["data"]["commodityGroupId"] == 29
        assert ext_body["data"]["commodityGroupName"] == "Hardware"
    finally:
        client.delete(f"/requests/{req_id}", headers=_auth(admin_token))
        client.patch(
            "/organizations/me/settings",
            json={
                "required_fields": [],
                "accounting_guidelines": None,
                "commodity_rules": None,
            },
            headers=_auth(admin_token),
        )


if __name__ == "__main__":
    test_full_user_journey()
    test_pdf_parse()
    test_extraction_without_api_key()
    test_activity_log_and_document()
    test_commodity_groups_expanded()
    test_suppliers_are_org_scoped_master_data()
    test_articles_catalog_paginated_and_searchable()
    test_seed_is_idempotent()
    test_demo_user_can_sign_in()
    test_approval_flow_with_roles()
    test_org_settings_required_fields()
    test_org_settings_admin_only()
    test_catalog_article_suggestions_and_negotiated_pricing()
    print("ALL SMOKE TESTS PASSED")
