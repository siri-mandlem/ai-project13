import unittest
from unittest.mock import patch

from sqlalchemy.engine import make_url

from backend.app import _database_uri, create_app
from backend.extensions import db
from backend.models import Appointment, MedicalRecord, User


class HospitalApplicationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            self.patient = self._user("patient@example.test", "patient")
            self.doctor = self._user("doctor@example.test", "doctor")
            self.admin = self._user("admin@example.test", "admin")
            db.session.add_all([self.patient, self.doctor, self.admin])
            db.session.commit()
            self.patient_id = self.patient.id
            self.doctor_id = self.doctor.id
            self.admin_id = self.admin.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    @staticmethod
    def _user(email, role):
        user = User(
            name=role.title(),
            email=email,
            role=role,
            specialty="Cardiology" if role == "doctor" else None,
        )
        user.set_password("correct-horse-battery-staple")
        return user

    def _login(self, email):
        return self.client.post(
            "/api/auth/login",
            json={"email": email, "password": "correct-horse-battery-staple"},
        )

    def _appointment(self, status="pending"):
        from datetime import datetime, timedelta, timezone

        with self.app.app_context():
            appointment = Appointment(
                patient_id=self.patient_id,
                doctor_id=self.doctor_id,
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=2),
                reason="General consultation",
                status=status,
            )
            db.session.add(appointment)
            db.session.commit()
            return appointment.id

    def test_home_health_and_database_readiness(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"CarePoint", home.get_data())
        home.close()
        script = self.client.get("/assets/js/script.js")
        self.assertEqual(script.status_code, 200)
        script.close()
        self.assertEqual(self.client.get("/health").get_json()["status"], "ok")
        self.assertEqual(self.client.get("/ready").get_json()["status"], "ready")

    def test_production_requires_secrets_and_normalizes_neon_url(self):
        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
                create_app()

        with patch.dict(
            "os.environ",
            {
                "DATABASE_URL": "postgres://user:secret@ep-example.neon.tech/hospital",
            },
            clear=True,
        ):
            uri = _database_uri()
        self.assertEqual(make_url(uri).drivername, "postgresql+psycopg2")
        self.assertTrue(uri.startswith("postgresql+psycopg2://"))
        self.assertIn("sslmode=require", uri)

        with patch.dict(
            "os.environ",
            {"DATABASE_URL": "postgresql://user:secret@db.example.test/hospital"},
            clear=True,
        ):
            uri = _database_uri()
        self.assertTrue(uri.startswith("postgresql+psycopg2://"))

    def test_patient_registration_and_role_restrictions(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "New Patient",
                "email": "new.patient@example.test",
                "password": "a-long-patient-password",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["user"]["role"], "patient")
        self.assertEqual(
            self.client.post(
                "/api/auth/register",
                json={
                    "name": "Attempted Admin",
                    "email": "bad@example.test",
                    "password": "a-long-patient-password",
                    "role": "admin",
                },
            ).status_code,
            400,
        )
        self.assertEqual(self.client.post("/api/doctors", json={}).status_code, 403)

    def test_patient_books_and_cancels_only_own_appointment(self):
        self._login("patient@example.test")
        from datetime import datetime, timedelta, timezone

        scheduled_at = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        response = self.client.post(
            "/api/appointments",
            json={
                "doctor_id": self.doctor_id,
                "scheduled_at": scheduled_at,
                "reason": "Annual checkup",
            },
        )
        self.assertEqual(response.status_code, 201)
        appointment_id = response.get_json()["appointment"]["id"]
        self.assertEqual(
            self.client.patch(
                f"/api/appointments/{appointment_id}",
                json={"status": "confirmed"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/appointments/{appointment_id}",
                json={"status": "cancelled"},
            ).status_code,
            200,
        )

    def test_doctor_manages_appointment_and_creates_record_for_patient(self):
        appointment_id = self._appointment()
        self._login("doctor@example.test")
        response = self.client.patch(
            f"/api/appointments/{appointment_id}",
            json={"status": "confirmed"},
        )
        self.assertEqual(response.status_code, 200)
        record_response = self.client.post(
            "/api/records",
            json={
                "appointment_id": appointment_id,
                "diagnosis": "Routine checkup",
                "notes": "Follow-up in six months.",
            },
        )
        self.assertEqual(record_response.status_code, 201)
        self.assertEqual(record_response.get_json()["record"]["patient_id"], self.patient_id)
        self.assertEqual(
            self.client.post(
                "/api/records",
                json={
                    "appointment_id": appointment_id,
                    "diagnosis": "Duplicate",
                    "notes": "",
                },
            ).status_code,
            409,
        )

    def test_patient_cannot_read_another_patients_records(self):
        appointment_id = self._appointment("confirmed")
        with self.app.app_context():
            other_patient = User(
                name="Other Patient",
                email="other@example.test",
                role="patient",
            )
            other_patient.set_password("correct-horse-battery-staple")
            db.session.add(other_patient)
            db.session.commit()
            appointment = db.session.get(Appointment, appointment_id)
            db.session.add(MedicalRecord(
                patient_id=appointment.patient_id,
                doctor_id=appointment.doctor_id,
                appointment_id=appointment.id,
                diagnosis="Private diagnosis",
                notes="Private note",
            ))
            db.session.commit()
        self._login("other@example.test")
        self.assertEqual(self.client.get("/api/records").get_json()["records"], [])

    def test_admin_creates_doctor_and_sees_summary_and_records(self):
        self._login("admin@example.test")
        created = self.client.post(
            "/api/doctors",
            json={
                "name": "Dr New",
                "email": "new.doctor@example.test",
                "specialty": "Pediatrics",
                "password": "a-long-doctor-password",
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["doctor"]["role"], "doctor")
        summary = self.client.get("/api/admin/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.get_json()["patients"], 1)
        self.assertEqual(summary.get_json()["doctors"], 2)
        self.assertEqual(self.client.get("/api/records").status_code, 200)


if __name__ == "__main__":
    unittest.main()
