from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from backend.extensions import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint(
            "role IN ('patient', 'doctor', 'admin')",
            name="ck_users_role",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="patient")
    phone = db.Column(db.String(40))
    specialty = db.Column(db.String(120))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "phone": self.phone,
            "specialty": self.specialty,
            "is_active": self.is_active,
        }


class Appointment(db.Model):
    __tablename__ = "appointments"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'confirmed', 'completed', 'cancelled')",
            name="ck_appointments_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    doctor_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    scheduled_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    reason = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )
    patient = db.relationship("User", foreign_keys=[patient_id])
    doctor = db.relationship("User", foreign_keys=[doctor_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_name": self.patient.name,
            "doctor_id": self.doctor_id,
            "doctor_name": self.doctor.name,
            "doctor_specialty": self.doctor.specialty,
            "scheduled_at": self.scheduled_at.isoformat(),
            "reason": self.reason,
            "status": self.status,
        }


class MedicalRecord(db.Model):
    __tablename__ = "medical_records"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    doctor_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    appointment_id = db.Column(
        db.Integer,
        db.ForeignKey("appointments.id"),
        nullable=False,
        unique=True,
    )
    diagnosis = db.Column(db.String(500), nullable=False)
    notes = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now
    )
    patient = db.relationship("User", foreign_keys=[patient_id])
    doctor = db.relationship("User", foreign_keys=[doctor_id])
    appointment = db.relationship("Appointment")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_name": self.patient.name,
            "doctor_id": self.doctor_id,
            "doctor_name": self.doctor.name,
            "appointment_id": self.appointment_id,
            "appointment_at": self.appointment.scheduled_at.isoformat(),
            "diagnosis": self.diagnosis,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }
