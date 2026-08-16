"""Offer tracking (spec section 14). Salary/terms are only ever what the
user actually enters -- never inferred or estimated."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.browser.adapters.generic import log_event
from app.models.application import Application
from app.models.enums import ApplicationEventType, OfferStatus
from app.models.offer import Offer


def create_offer(
    db: Session, application: Application, company: str | None = None, role: str | None = None,
    salary: int | None = None, currency: str | None = None, employment_type: str | None = None,
    location: str | None = None, start_date: date | None = None, notes: str | None = None,
) -> Offer:
    offer = Offer(
        application_id=application.id, company=company, role=role, salary=salary, currency=currency,
        employment_type=employment_type, location=location, start_date=start_date, notes=notes,
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    log_event(db, application, ApplicationEventType.OFFER_RECEIVED, f"Offer recorded: {role or 'role'} at {company or 'company'}.", {"offer_id": offer.id})
    return offer


def list_offers(db: Session, application_id: int) -> list[Offer]:
    return db.execute(select(Offer).where(Offer.application_id == application_id).order_by(Offer.created_at)).scalars().all()


def update_offer(db: Session, offer: Offer, status: OfferStatus | None = None, notes: str | None = None) -> Offer:
    if status is not None:
        offer.status = status
    if notes is not None:
        offer.notes = notes
    db.commit()
    db.refresh(offer)
    return offer
