"""Domains, table archetypes and splits for the synthetic corpus (spec 10.1). Archetype column entries are semantics from
semantics.py; a trailing '?' marks a column that appears about 60% of the time.

Split (spec table is garbled in the PDF; confirm with lead): train = Hospital, Bank, HR, E-commerce, Government;
validation = Telecom, Humanitarian NGO; held-out test = School. St. Aster is the demo and is never trained on.
"""

# tables per domain (spec 10.1)
COUNTS = {"hospital": 180, "bank": 180, "hr": 150, "ecommerce": 150, "government": 150, "telecom": 140, "ngo": 120, "school": 130}
SPLIT = {"hospital": "train", "bank": "train", "hr": "train", "ecommerce": "train", "government": "train",
         "telecom": "validation", "ngo": "validation", "school": "test"}

PERSON = ["full_name", "dob", "national_id", "address", "phone?", "email?", "gender?", "person_id"]
SESSION = ["person_id", "token_hash", "expires_at", "created?"]
OTP = ["phone", "otp_code", "expires_at"]

ARCHETYPES = {
    "hospital": {
        "patient_master": PERSON, "visits": ["person_id", "clin_ts", "icd10", "clin_notes", "blood_group?"],
        "lab_orders": ["person_id", "loinc", "lab_value", "lab_unit", "clin_ts"], "prescriptions": ["person_id", "medication", "clin_ts", "allergy?"],
        "genetic_panels": ["person_id", "gene_panel", "variant", "zygosity", "genotype?"], "immunization_log": ["person_id", "vaccine", "dose_date", "growth?"],
        "billing": ["person_id", "amount", "currency", "insurer", "paid_at"], "appointments": ["person_id", "sms_text", "send_at", "slot?"],
        "staff_login": SESSION, "otp_log": OTP,
    },
    "bank": {
        "customers": PERSON, "accounts": ["person_id", "card_number", "amount", "currency", "created?"], "cards": ["person_id", "card_number", "expires_at?", "status"],
        "transactions": ["person_id", "amount", "currency", "merchant", "paid_at"], "kyc_documents": ["person_id", "doc_number", "full_name?", "address?", "dob?"],
        "online_sessions": SESSION, "otp_codes": OTP, "insurance_policies": ["person_id", "insurer", "icd10?", "blood_group?", "allergy?", "amount"], "loan_applications": ["person_id", "amount", "insurer?", "national_id?", "address?"],
        "sms_alerts": ["person_id", "sms_text", "send_at"],
    },
    "hr": {
        "employees": PERSON, "payroll": ["person_id", "amount", "currency", "paid_at"], "personnel_files": ["person_id", "case_notes", "doc_number?", "dob?"],
        "benefits": ["person_id", "insurer", "amount?"], "medical_leave": ["person_id", "icd10", "clin_notes?", "clin_ts"],
        "sso_sessions": SESSION, "occupational_health": ["person_id", "blood_group", "allergy", "icd10?", "vaccine?"], "shift_schedule": ["person_id", "slot", "send_at"], "otp_codes": OTP, "directory": ["full_name", "email", "phone", "person_id"],
    },
    "ecommerce": {
        "customers": ["full_name", "email", "phone", "address", "person_id", "created?"], "orders": ["person_id", "amount", "currency", "paid_at", "status"],
        "payments": ["person_id", "card_number", "amount", "currency", "paid_at"], "carts": ["token_hash", "cart_item", "send_at"],
        "sessions": SESSION, "reviews": ["person_id", "product_review", "created", "label?"], "shipping": ["person_id", "address", "phone", "full_name?"],
        "otp_codes": OTP, "product_catalog": ["label", "amount", "country", "version?", "flag?"],
    },
    "government": {
        "citizens": PERSON, "land_records": ["national_id", "full_name", "doc_number", "address", "created?"], "tax_filings": ["person_id", "amount", "currency", "national_id?"],
        "licences": ["person_id", "doc_number", "dob", "address?"], "form_drafts": ["token_hash", "sms_text", "send_at"], "benefit_claims": ["national_id", "amount", "status", "paid_at?"],
        "portal_sessions": SESSION, "otp_codes": OTP, "student_records": ["person_id", "grade", "teacher_remarks", "dob?", "label?"],
        "biobank_samples": ["person_id", "gene_panel", "variant", "genotype?", "zygosity?"], "disability_registry": ["person_id", "icd10", "blood_group", "allergy?", "growth?"], "school_enrolment": ["person_id", "full_name", "grade", "vaccine?", "slot?"], "service_routes": ["label", "status", "version", "country?"],
    },
    "telecom": {
        "subscribers": PERSON, "call_records": ["person_id", "phone", "send_at", "version?"], "routing_cache": ["label", "country", "version", "created?"],
        "sim_registry": ["person_id", "doc_number", "created?"], "billing": ["person_id", "amount", "currency", "paid_at"], "otp_codes": OTP,
        "support_tickets": ["person_id", "product_review", "status", "created?"], "sms_queue": ["phone", "sms_text", "send_at"], "portal_sessions": SESSION,
    },
    "ngo": {
        "beneficiaries": PERSON, "case_files": ["person_id", "case_notes", "dob?", "address?"], "genomic_screening": ["person_id", "variant", "zygosity", "gene_panel?", "clin_ts?"], "health_screening": ["person_id", "icd10", "vaccine", "growth", "clin_ts?"],
        "donations": ["person_id", "amount", "currency", "paid_at"], "sms_queue": ["person_id", "sms_text", "send_at"], "scheduled_visits": ["person_id", "slot", "send_at"], "payments_due": ["person_id", "amount", "currency", "paid_at"], "volunteer_login": SESSION,
        "distribution_log": ["person_id", "label", "send_at"], "otp_codes": OTP, "household_registry": ["person_id", "full_name", "national_id?", "phone", "address"],
    },
    "school": {
        "students": ["full_name", "dob", "address", "person_id", "gender?", "national_id?"], "report_cards": ["person_id", "grade", "teacher_remarks", "label?"],
        "health_records": ["person_id", "vaccine", "blood_group", "allergy", "dose_date?"], "attendance": ["person_id", "send_at", "status"],
        "timetable": ["slot", "label", "version?"], "fees": ["person_id", "amount", "currency", "paid_at"], "guardian_contacts": ["person_id", "phone", "email", "full_name"],
        "sms_queue": ["phone", "sms_text", "send_at"], "login_sessions": SESSION, "otp_codes": OTP,
    },
}

# St. Aster General: the demo tables, labelled by hand from the spec. Used only for evaluation; real names come from records-db.
ST_ASTER = {
    "patients": {"rows": 50000, "cols": [("full_name", "full_name"), ("date_of_birth", "dob"), ("national_id", "national_id"), ("address", "address"), ("phone", "phone"), ("blood_group", "blood_group")]},
    "encounters": {"rows": 200000, "cols": [("patient_id", "person_id"), ("admitted_at", "clin_ts"), ("diagnosis_icd10", "icd10"), ("clinician_notes", "clin_notes")]},
    "genomics_results": {"rows": 8000, "cols": [("patient_id", "person_id"), ("gene_panel", "gene_panel"), ("variant_hgvs", "variant"), ("zygosity", "zygosity")]},
    "child_immunizations": {"rows": 30000, "cols": [("child_patient_id", "person_id"), ("vaccine_code", "vaccine"), ("dose_date", "dose_date")]},
    "lab_results": {"rows": 400000, "cols": [("patient_id", "person_id"), ("test_code_loinc", "loinc"), ("value", "lab_value"), ("unit", "lab_unit"), ("collected_at", "clin_ts")]},
    "billing_invoices": {"rows": 150000, "cols": [("patient_id", "person_id"), ("amount", "amount"), ("currency", "currency"), ("insurer", "insurer"), ("paid_at", "paid_at")]},
    "appointment_reminders": {"rows": 60000, "cols": [("patient_id", "person_id"), ("sms_text", "sms_text"), ("send_at", "send_at")]},
    "staff_sessions": {"rows": 5000, "cols": [("staff_id", "person_id"), ("token_hash", "token_hash"), ("expires_at", "expires_at")]},
    "otp_codes": {"rows": 10000, "cols": [("phone", "phone"), ("code", "otp_code"), ("expires_at", "expires_at")]},
}
