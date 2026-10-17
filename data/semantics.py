"""Column semantics for the synthetic training corpus: category label, SQL type, name variants, seeded value generator.

Labels come from the team-written mapping here (also dumped to labels.yaml); policy periods come from policy.yaml, never from here.
All values are synthetic.
"""
import string

from faker import Faker

fake = Faker()
Faker.seed(7)


def _digits(r, n):
    return "".join(r.choice(string.digits) for _ in range(n))


def _hex(r, n):
    return "".join(r.choice("0123456789abcdef") for _ in range(n))


def _alnum(r, n):
    return "".join(r.choice(string.ascii_letters + string.digits + "_-") for _ in range(n))


def _date(r, lo, hi):
    return f"{r.randint(lo, hi)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}"


def _ts(r):
    return f"{_date(r, 2022, 2026)} {r.randint(0, 23):02d}:{r.randint(0, 59):02d}:{r.randint(0, 59):02d}"


def _nid(r):
    return r.choice([lambda: f"{_digits(r, 3)}-{_digits(r, 2)}-{_digits(r, 4)}", lambda: _digits(r, 12),
                     lambda: "".join(r.choice(string.ascii_uppercase) for _ in range(5)) + _digits(r, 4) + r.choice(string.ascii_uppercase)])()


def _icd(r):
    return f"{r.choice('ABCDEFGHIJKLMNOPQRST')}{_digits(r, 2)}" + (f".{r.choice(['9', '0', '1', '10', '21'])}" if r.random() < .7 else "")


def _hgvs(r):
    return r.choice([f"NM_{_digits(r, 6)}.{r.randint(1, 4)}:c.{r.randint(1, 9000)}{r.choice('ACGT')}>{r.choice('ACGT')}",
                     f"c.{r.randint(1, 900)}_{r.randint(901, 999)}del{r.choice('ACGT')}{r.choice('ACGT')}", f"p.{r.choice(['Arg', 'Gly', 'Leu'])}{r.randint(10, 800)}Ter"])


def _jwt(r):
    return f"eyJ{_alnum(r, 20)}.{_alnum(r, 40)}.{_alnum(r, 30)}"


def _pid(r):
    return r.choice([lambda: f"P{_digits(r, 7)}", lambda: _hex(r, 8) + "-" + _hex(r, 4) + "-" + _hex(r, 4) + "-" + _hex(r, 4) + "-" + _hex(r, 12), lambda: _digits(r, r.randint(5, 8))])()


def _phone(r):
    return r.choice([lambda: f"+91 {_digits(r, 5)} {_digits(r, 5)}", lambda: f"+1 ({_digits(r, 3)}) {_digits(r, 3)}-{_digits(r, 4)}", lambda: _digits(r, 10)])()


def _sms(r):
    return r.choice(["Reminder: your appointment is on {d} at {t}. Reply YES to confirm.", "Hello, your slot {d} {t} is booked.",
                     "Your order ships on {d}.", "Class resumes {d} at {t}."]).format(d=_date(r, 2026, 2026), t=f"{r.randint(8, 17)}:{r.choice(['00', '30'])}")


# sem -> (category, sql_type, [name variants], generator(r))
SEMANTICS = {
    # identity
    "full_name": ("identity", "text", ["full_name", "name", "patient_name", "customer_name", "fullname", "nm"], lambda r: fake.name()),
    "first_name": ("identity", "text", ["first_name", "fname", "given_name", "forename"], lambda r: fake.first_name()),
    "last_name": ("identity", "text", ["last_name", "lname", "surname", "family_name"], lambda r: fake.last_name()),
    "dob": ("identity", "date", ["date_of_birth", "dob", "birth_dt", "birthdate", "born_on", "DateOfBirth"], lambda r: _date(r, 1930, 2012)),
    "national_id": ("identity", "text", ["national_id", "nid", "ssn", "aadhaar_no", "tax_id", "citizen_id_no", "id_number"], _nid),
    "address": ("identity", "text", ["address", "addr", "home_address", "street_address", "residence"], lambda r: fake.address().replace("\n", ", ")),
    "doc_number": ("identity", "text", ["passport_no", "doc_number", "kyc_doc_no", "license_no", "parcel_owner_id"], lambda r: "".join(r.choice(string.ascii_uppercase) for _ in range(2)) + _digits(r, 7)),
    "gender": ("identity", "text", ["gender", "sex", "gender_code"], lambda r: r.choice(["F", "M", "X", "Female", "Male"])),
    "case_notes": ("identity", "text", ["case_notes", "personnel_notes", "review_text", "protection_notes"], lambda r: fake.sentence(nb_words=r.randint(8, 22))),
    # contact
    "phone": ("contact", "text", ["phone", "mobile", "phone_number", "contact_no", "tel", "msisdn", "guardian_phone"], _phone),
    "email": ("contact", "text", ["email", "email_address", "mail", "contact_email", "guardian_email"], lambda r: fake.email()),
    # clinical
    "icd10": ("clinical", "text", ["diagnosis_icd10", "icd_code", "dx_code", "diagnosis", "condition_code"], _icd),
    "loinc": ("clinical", "text", ["test_code_loinc", "loinc", "lab_test_code", "assay_code"], lambda r: f"{_digits(r, r.randint(3, 5))}-{r.randint(0, 9)}"),
    "clin_notes": ("clinical", "text", ["clinician_notes", "notes", "progress_note", "soap_text", "doctor_remarks"], lambda r: fake.paragraph(nb_sentences=r.randint(1, 3))),
    "blood_group": ("clinical", "text", ["blood_group", "blood_type", "abo_rh", "bg"], lambda r: r.choice(["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"])),
    "lab_value": ("clinical", "text", ["value", "result_value", "lab_value", "reading", "measurement"], lambda r: f"{r.uniform(0.1, 400):.1f}"),
    "lab_unit": ("clinical", "text", ["unit", "uom", "result_unit", "units"], lambda r: r.choice(["mg/dL", "mmol/L", "g/L", "IU/L", "%"])),
    "medication": ("clinical", "text", ["medication", "drug_name", "rx_item", "prescription", "med"], lambda r: r.choice(["Metformin 500mg", "Amoxicillin 250mg", "Atorvastatin 20mg", "Salbutamol inhaler"])),
    "clin_ts": ("clinical", "timestamp", ["admitted_at", "visit_ts", "collected_at", "encounter_time", "discharged_at", "sampled_on"], _ts),
    "allergy": ("clinical", "text", ["allergy", "allergen", "adverse_reaction"], lambda r: r.choice(["penicillin", "latex", "peanuts", "none", "sulfa"])),
    # genetic
    "variant": ("genetic", "text", ["variant_hgvs", "variant", "hgvs", "mutation", "snv_notation"], _hgvs),
    "gene_panel": ("genetic", "text", ["gene_panel", "panel_name", "gene_set", "assay_panel"], lambda r: r.choice(["BRCA1/BRCA2", "CFTR full", "HBB panel", "Lynch syndrome panel", "TP53"])),
    "zygosity": ("genetic", "text", ["zygosity", "allele_state", "genotype_state"], lambda r: r.choice(["heterozygous", "homozygous", "hemizygous"])),
    "genotype": ("genetic", "text", ["genotype", "snp_call", "allele_call"], lambda r: f"rs{_digits(r, 7)}:{r.choice('ACGT')}/{r.choice('ACGT')}"),
    # child_health
    "vaccine": ("child_health", "text", ["vaccine_code", "vaccine", "immunisation_type", "vax", "antigen"], lambda r: r.choice(["BCG", "OPV3", "MMR1", "DTP2", "HEPB", "CVX-08", "CVX-20"])),
    "dose_date": ("child_health", "date", ["dose_date", "vaccinated_on", "immunised_at", "shot_date"], lambda r: _date(r, 2016, 2026)),
    "growth": ("child_health", "text", ["growth_percentile", "height_for_age", "weight_for_age", "muac_cm"], lambda r: f"{r.uniform(1, 99):.1f}"),
    "grade": ("child_health", "text", ["grade", "report_grade", "final_mark", "term_result", "gpa"], lambda r: r.choice(["A", "B+", "B", "C", "A-", "78", "91", "64"])),
    "teacher_remarks": ("child_health", "text", ["teacher_remarks", "conduct_note", "learning_support_note", "counsellor_comment"], lambda r: fake.sentence(nb_words=r.randint(6, 18))),
    # financial
    "amount": ("financial", "numeric", ["amount", "invoice_total", "balance", "txn_amount", "salary", "total_due", "income"], lambda r: f"{r.uniform(5, 90000):.2f}"),
    "currency": ("financial", "text", ["currency", "ccy", "currency_code"], lambda r: r.choice(["USD", "INR", "EUR", "GBP", "KES"])),
    "insurer": ("financial", "text", ["insurer", "payer", "insurance_co", "plan_provider"], lambda r: fake.company()),
    "paid_at": ("financial", "timestamp", ["paid_at", "payment_ts", "settled_on", "invoice_date"], _ts),
    "card_number": ("financial", "text", ["card_number", "pan", "account_no", "iban", "acct_number"], lambda r: _digits(r, 16) if r.random() < .6 else "IN" + _digits(r, 18)),
    "merchant": ("financial", "text", ["merchant", "payee", "vendor_name", "counterparty"], lambda r: fake.company()),
    # pseudonymous_id
    "person_id": ("pseudonymous_id", "text", ["patient_id", "customer_id", "employee_id", "student_id", "user_id", "subscriber_id", "child_patient_id", "beneficiary_id", "member_ref", "staff_id", "case_id"], _pid),
    # scheduling
    "sms_text": ("scheduling", "text", ["sms_text", "message_body", "reminder_text", "notification_text", "draft_text"], _sms),
    "send_at": ("scheduling", "timestamp", ["send_at", "scheduled_for", "slot_start", "due_ts", "remind_at", "added_to_cart_at"], _ts),
    "slot": ("scheduling", "text", ["timetable_slot", "shift_slot", "class_period", "time_window"], lambda r: f"{r.choice(['Mon', 'Tue', 'Wed', 'Thu', 'Fri'])} {r.randint(8, 16):02d}:00-{r.randint(9, 17):02d}:00"),
    "cart_item": ("scheduling", "text", ["cart_item", "basket_sku", "draft_form_field"], lambda r: f"SKU-{_digits(r, 6)}x{r.randint(1, 4)}"),
    # auth_secret
    "token_hash": ("auth_secret", "text", ["token_hash", "session_token", "api_key_hash", "csrf_token", "refresh_token", "pw_hash"], lambda r: r.choice([lambda: _hex(r, 64), lambda: _jwt(r), lambda: _alnum(r, 44)])()),
    "otp_code": ("auth_secret", "text", ["code", "otp", "otp_code", "verification_code", "pin"], lambda r: _digits(r, 6)),
    "expires_at": ("auth_secret", "timestamp", ["expires_at", "valid_until", "expiry_ts", "ttl_at"], _ts),
    # non_sensitive
    "status": ("non_sensitive", "text", ["status", "state", "is_active_flag", "record_status"], lambda r: r.choice(["ACTIVE", "CLOSED", "PENDING", "NEW"])),
    "country": ("non_sensitive", "text", ["country_code", "locale", "region_code", "lang"], lambda r: r.choice(["IN", "US", "KE", "GB", "DE"])),
    "version": ("non_sensitive", "integer", ["row_version", "revision", "schema_ver", "sort_order", "page_size"], lambda r: str(r.randint(0, 40))),
    "created": ("non_sensitive", "timestamp", ["created_at", "updated_at", "etl_loaded_at", "last_sync"], _ts),
    "flag": ("non_sensitive", "boolean", ["is_deleted", "enabled", "archived", "verified_flag"], lambda r: r.choice(["t", "f"])),
    "label": ("non_sensitive", "text", ["label", "category_name", "title", "description", "route_prefix"], lambda r: fake.word()),
    "product_review": ("non_sensitive", "text", ["review_text", "comment", "feedback"], lambda r: fake.sentence(nb_words=r.randint(5, 20))),
}


def categories() -> dict:
    return {k: v[0] for k, v in SEMANTICS.items()}
