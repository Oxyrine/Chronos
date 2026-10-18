"""Independent, deterministic St. Aster fixtures. Never imports classifier training data.

Writes COPY CSVs, init SQL and measured JSON row sizes. For a fresh database only:
python3 demo/records-db/gen_data.py; docker compose -f demo/compose.yml up -d
"""
import argparse
import csv
import datetime as dt
import json
import random
from pathlib import Path

COUNTS = {"patients": 50000, "encounters": 200000, "genomics_results": 8000,
          "child_immunizations": 30000, "lab_results": 400000, "billing_invoices": 150000,
          "appointment_reminders": 60000, "staff_sessions": 5000, "otp_codes": 10000}
SCHEMAS = {
    "patients": "patient_id integer PRIMARY KEY, full_name text, dob date, national_id text, address text, phone text, blood_group text",
    "encounters": "encounter_id integer PRIMARY KEY, patient_id integer REFERENCES patients(patient_id), admitted_at timestamp, diagnosis_icd10 text, clinician_notes text",
    "genomics_results": "result_id integer PRIMARY KEY, patient_id integer REFERENCES patients(patient_id), gene_panel text, variant_hgvs text, zygosity text",
    "child_immunizations": "immunization_id integer PRIMARY KEY, child_patient_id integer REFERENCES patients(patient_id), vaccine_code text, dose_date date",
    "lab_results": "result_id integer PRIMARY KEY, patient_id integer REFERENCES patients(patient_id), test_code_loinc text, value text, unit text, collected_at timestamp",
    "billing_invoices": "invoice_id integer PRIMARY KEY, patient_id integer REFERENCES patients(patient_id), amount numeric(12,2), currency text, insurer text, paid_at timestamp",
    "appointment_reminders": "reminder_id integer PRIMARY KEY, patient_id integer REFERENCES patients(patient_id), sms_text text, send_at timestamp",
    "staff_sessions": "session_id integer PRIMARY KEY, staff_id integer, token_hash text, expires_at timestamp",
    "otp_codes": "otp_id integer PRIMARY KEY, phone text, code text, expires_at timestamp",
}

def generate(out, scale=1.0, seed=42):
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    counts = {k: max(1, int(v * scale)) for k, v in COUNTS.items()}
    names = [f"{rng.choice(['Aarav','Meera','Isha','Kabir','Sana','Dev','Leela','Rehan'])} {rng.choice(['Rao','Das','Shah','Khan','Iyer','Singh','Patel'])}" for _ in range(5000)]
    addresses = [f"{i+1} {rng.choice(['Park','Lake','Temple','Market'])} Road, Ward {rng.randrange(1,50)}, Pune {411000+rng.randrange(100)}" for i in range(5000)]
    date0 = dt.date(2026, 10, 17)
    def stamp(days=0):
        return f"{date0 + dt.timedelta(days=days)}T{rng.randrange(24):02d}:{rng.randrange(60):02d}:00"
    def phone():
        return f"+91{rng.randrange(7000000000,9999999999)}"
    facts = {}
    sql = ["\\set ON_ERROR_STOP on", "BEGIN;"]
    for table, count in counts.items():
        columns = [col.split()[0] for col in SCHEMAS[table].split(", ") if not col.startswith("2)")]
        # numeric(12,2) has no space after its comma; splitting stays unambiguous.
        total_bytes = 0
        with (out / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for i in range(1, count + 1):
                patient = rng.randrange(1, counts["patients"] + 1)
                if table == "patients":
                    row = [i, rng.choice(names), str(date0-dt.timedelta(days=rng.randrange(365,33000))), f"SYN-{rng.randrange(10**11,10**12)}", rng.choice(addresses), phone(), rng.choice(["A+","B+","O+","AB+","O-"])]
                elif table == "encounters":
                    row = [i, patient, stamp(-rng.randrange(3650)), rng.choice(["E11.9","I10","J06.9","Z00.0","M54.5"]), rng.choice(["Synthetic follow-up: monitor blood pressure and review in two weeks.","Synthetic examination: stable, no acute symptoms.","Synthetic consultation: family history reviewed; routine screening advised."])]
                elif table == "genomics_results":
                    row = [i, patient, rng.choice(["BRCA1/BRCA2","CFTR","HBB","CYP2C19"]), rng.choice(["NM_007294.4:c.68_69delAG","NM_000492.4:c.1521_1523delCTT","NM_000518.5:c.20A>T"]), rng.choice(["heterozygous","homozygous"])]
                elif table == "child_immunizations":
                    row = [i, patient, rng.choice(["BCG","OPV","DTP","MMR","HepB"]), str(date0-dt.timedelta(days=rng.randrange(1000)))]
                elif table == "lab_results":
                    code, unit = rng.choice([("718-7","g/dL"),("4548-4","%"),("2345-7","mg/dL"),("2160-0","mg/dL")])
                    row = [i, patient, code, f"{rng.uniform(1,150):.2f}", unit, stamp(-rng.randrange(730))]
                elif table == "billing_invoices":
                    row = [i, patient, f"{rng.uniform(100,100000):.2f}", "INR", rng.choice(["Self pay","Synthetic Health Cover","St Aster Fund"]), stamp(-rng.randrange(1000))]
                elif table == "appointment_reminders":
                    row = [i, patient, f"Synthetic St Aster reminder: patient {patient}, clinic follow-up tomorrow at 10:00.", stamp(rng.randrange(14))]
                elif table == "staff_sessions":
                    row = [i, rng.randrange(1,501), f"{rng.getrandbits(256):064x}", stamp(1)]
                else:
                    row = [i, phone(), f"{rng.randrange(1000000):06d}", stamp()]
                writer.writerow(row)
                total_bytes += len(json.dumps(dict(zip(columns, row)), separators=(",", ":")).encode())
        facts[table] = {"records": count, "store": "records-db", "mean_record_bytes": round(total_bytes / count, 3)}
        sql += [f"CREATE TABLE public.{table} ({SCHEMAS[table]});", f"\\copy public.{table} FROM '/docker-entrypoint-initdb.d/{table}.csv' WITH (FORMAT csv);"]
        if table not in ("patients", "staff_sessions", "otp_codes"):
            key = "child_patient_id" if table == "child_immunizations" else "patient_id"
            sql.append(f"CREATE INDEX ON public.{table} ({key});")
    sql += ["COMMIT;", "ANALYZE;"]
    (out / "00-init.sql").write_text("\n".join(sql) + "\n", encoding="utf-8")
    (out / "table_facts.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    return facts

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("generated"))
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--update-topology", action="store_true")
    args = parser.parse_args()
    if args.scale <= 0 or args.scale > 1:
        parser.error("scale must be in (0,1]")
    facts = generate(args.output, args.scale)
    if args.update_topology:
        path = Path(__file__).parents[1] / "topology.yaml"
        topology = json.loads(path.read_text())  # JSON is valid YAML; no extra package in base image
        topology["tables"] = facts
        path.write_text(json.dumps(topology, indent=2) + "\n")
    print(json.dumps({"rows": sum(x["records"] for x in facts.values()), "tables": len(facts), "output": str(args.output)}))
