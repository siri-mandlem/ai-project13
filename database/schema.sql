CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('patient', 'doctor', 'admin')),
    phone VARCHAR(40),
    specialty VARCHAR(120),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS appointments (
    id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT NOT NULL REFERENCES users(id),
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    scheduled_at TIMESTAMPTZ NOT NULL,
    reason VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'confirmed', 'completed', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS medical_records (
    id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT NOT NULL REFERENCES users(id),
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    appointment_id BIGINT NOT NULL UNIQUE REFERENCES appointments(id),
    diagnosis VARCHAR(500) NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_appointments_patient_id ON appointments(patient_id);
CREATE INDEX IF NOT EXISTS ix_appointments_doctor_id ON appointments(doctor_id);
CREATE INDEX IF NOT EXISTS ix_appointments_scheduled_at ON appointments(scheduled_at);
CREATE INDEX IF NOT EXISTS ix_medical_records_patient_id ON medical_records(patient_id);
CREATE INDEX IF NOT EXISTS ix_medical_records_doctor_id ON medical_records(doctor_id);
