from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request, session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.auth import current_user, login_required, roles_required
from backend.extensions import db
from backend.models import Appointment, MedicalRecord, User


api = Blueprint("api", __name__, url_prefix="/api")
VALID_APPOINTMENT_STATUSES = {"pending", "confirmed", "completed", "cancelled"}


def _json_body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _required_text(body: dict, key: str, maximum: int) -> str | None:
    value = body.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and len(value) <= maximum else None


def _parse_scheduled_at(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed if parsed > datetime.now(timezone.utc) else None


@api.get("/auth/me")
def auth_me():
    user = current_user()
    return jsonify({"user": user.to_dict() if user else None})


@api.post("/auth/register")
def register_patient():
    body = _json_body()
    name = _required_text(body, "name", 120)
    email = _required_text(body, "email", 254)
    password = body.get("password")
    phone = _required_text(body, "phone", 40) if body.get("phone") else None
    if not name or not email or "@" not in email or not isinstance(password, str):
        return jsonify({"error": "Enter a valid name, email, and password."}), 400
    if len(password) < 12 or len(password) > 256:
        return jsonify({"error": "Password must be between 12 and 256 characters."}), 400
    if body.get("role", "patient") != "patient":
        return jsonify({"error": "Public registration is available for patients only."}), 400

    user = User(name=name, email=email.lower(), role="patient", phone=phone)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "An account with that email already exists."}), 409
    session.clear()
    session["user_id"] = user.id
    session.permanent = True
    return jsonify({"user": user.to_dict()}), 201


@api.post("/auth/login")
def login():
    body = _json_body()
    email = _required_text(body, "email", 254)
    password = body.get("password")
    user = (
        db.session.scalar(select(User).where(User.email == email.lower()))
        if email
        else None
    )
    if (
        user is None
        or not isinstance(password, str)
        or not user.is_active
        or not user.check_password(password)
    ):
        return jsonify({"error": "Email or password is incorrect."}), 401
    session.clear()
    session["user_id"] = user.id
    session.permanent = True
    return jsonify({"user": user.to_dict()})


@api.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"message": "Signed out."})


@api.get("/doctors")
def list_doctors():
    doctors = db.session.scalars(
        select(User)
        .where(User.role == "doctor", User.is_active.is_(True))
        .order_by(User.name)
    ).all()
    return jsonify({
        "doctors": [
            {
                "id": doctor.id,
                "name": doctor.name,
                "specialty": doctor.specialty,
            }
            for doctor in doctors
        ]
    })


@api.post("/doctors")
@roles_required("admin")
def create_doctor():
    body = _json_body()
    name = _required_text(body, "name", 120)
    email = _required_text(body, "email", 254)
    specialty = _required_text(body, "specialty", 120)
    password = body.get("password")
    if (
        not name
        or not email
        or "@" not in email
        or not specialty
        or not isinstance(password, str)
        or len(password) < 12
        or len(password) > 256
    ):
        return jsonify({
            "error": "Enter a valid name, email, specialty, and password of at least 12 characters."
        }), 400
    doctor = User(
        name=name,
        email=email.lower(),
        role="doctor",
        specialty=specialty,
        phone=_required_text(body, "phone", 40) if body.get("phone") else None,
    )
    doctor.set_password(password)
    db.session.add(doctor)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "An account with that email already exists."}), 409
    return jsonify({"doctor": doctor.to_dict()}), 201


@api.get("/appointments")
@login_required
def list_appointments():
    user = g.current_user
    query = select(Appointment).order_by(Appointment.scheduled_at.desc())
    if user.role == "patient":
        query = query.where(Appointment.patient_id == user.id)
    elif user.role == "doctor":
        query = query.where(Appointment.doctor_id == user.id)
    appointments = db.session.scalars(query).all()
    return jsonify({"appointments": [item.to_dict() for item in appointments]})


@api.post("/appointments")
@roles_required("patient")
def create_appointment():
    body = _json_body()
    scheduled_at = _parse_scheduled_at(body.get("scheduled_at"))
    reason = _required_text(body, "reason", 500)
    try:
        doctor_id = int(body.get("doctor_id"))
    except (TypeError, ValueError):
        doctor_id = 0
    doctor = db.session.get(User, doctor_id)
    if not scheduled_at or not reason or doctor is None or doctor.role != "doctor" or not doctor.is_active:
        return jsonify({"error": "Choose an active doctor, a future date, and enter a reason."}), 400

    conflict = db.session.scalar(
        select(Appointment.id).where(
            Appointment.doctor_id == doctor.id,
            Appointment.scheduled_at == scheduled_at,
            Appointment.status.in_(("pending", "confirmed")),
        )
    )
    if conflict is not None:
        return jsonify({"error": "That doctor already has an appointment at this time."}), 409

    appointment = Appointment(
        patient_id=g.current_user.id,
        doctor_id=doctor.id,
        scheduled_at=scheduled_at,
        reason=reason,
    )
    db.session.add(appointment)
    db.session.commit()
    return jsonify({"appointment": appointment.to_dict()}), 201


@api.patch("/appointments/<int:appointment_id>")
@login_required
def update_appointment(appointment_id: int):
    appointment = db.session.get(Appointment, appointment_id)
    if appointment is None:
        return jsonify({"error": "Appointment not found."}), 404
    body = _json_body()
    new_status = body.get("status")
    if new_status not in VALID_APPOINTMENT_STATUSES:
        return jsonify({"error": "Choose a valid appointment status."}), 400

    user = g.current_user
    if user.role == "patient":
        if appointment.patient_id != user.id or new_status != "cancelled":
            return jsonify({"error": "Patients may only cancel their own appointments."}), 403
        if appointment.status not in {"pending", "confirmed"}:
            return jsonify({"error": "This appointment can no longer be cancelled."}), 409
    elif user.role == "doctor":
        if appointment.doctor_id != user.id or new_status not in {"confirmed", "completed", "cancelled"}:
            return jsonify({"error": "Doctors may only update their own appointments."}), 403
    elif user.role != "admin":
        return jsonify({"error": "You do not have permission for this action."}), 403
    appointment.status = new_status
    db.session.commit()
    return jsonify({"appointment": appointment.to_dict()})


@api.get("/records")
@login_required
def list_records():
    user = g.current_user
    query = select(MedicalRecord).order_by(MedicalRecord.created_at.desc())
    if user.role == "patient":
        query = query.where(MedicalRecord.patient_id == user.id)
    elif user.role == "doctor":
        query = query.where(MedicalRecord.doctor_id == user.id)
    records = db.session.scalars(query).all()
    return jsonify({"records": [record.to_dict() for record in records]})


@api.post("/records")
@roles_required("doctor")
def create_record():
    body = _json_body()
    diagnosis = _required_text(body, "diagnosis", 500)
    notes = body.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 10000:
        return jsonify({"error": "Notes must be 10,000 characters or fewer."}), 400
    try:
        appointment_id = int(body.get("appointment_id"))
    except (TypeError, ValueError):
        appointment_id = 0
    appointment = db.session.get(Appointment, appointment_id)
    if (
        not diagnosis
        or appointment is None
        or appointment.doctor_id != g.current_user.id
        or appointment.status not in {"confirmed", "completed"}
    ):
        return jsonify({
            "error": "Select one of your confirmed or completed appointments and enter a diagnosis."
        }), 400
    record = MedicalRecord(
        patient_id=appointment.patient_id,
        doctor_id=appointment.doctor_id,
        appointment_id=appointment.id,
        diagnosis=diagnosis,
        notes=notes.strip(),
    )
    db.session.add(record)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A medical record already exists for this appointment."}), 409
    return jsonify({"record": record.to_dict()}), 201


@api.get("/admin/summary")
@roles_required("admin")
def admin_summary():
    return jsonify({
        "patients": db.session.scalar(
            select(db.func.count()).select_from(User).where(User.role == "patient")
        ),
        "doctors": db.session.scalar(
            select(db.func.count()).select_from(User).where(User.role == "doctor")
        ),
        "appointments": db.session.scalar(select(db.func.count()).select_from(Appointment)),
        "records": db.session.scalar(select(db.func.count()).select_from(MedicalRecord)),
    })
