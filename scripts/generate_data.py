"""
Generates a synthetic payment-transactions dataset and writes one CSV per table.

The point of this script is NOT just to make random data. The failure rate is
deliberately skewed so there are real patterns to find in the SQL later:
  - one bank fails much more than the rest
  - failures spike in the 12am-3am server window
  - the old Android build fails more than newer clients
  - a few payment modes are shakier than others
These effects stack, so the worst pockets (bad bank + old device + late night)
end up looking really bad, which is what makes the analysis feel like an actual
investigation instead of a coin toss.

Run:  python scripts/generate_data.py --rows 100000
"""

import argparse
import csv
import os
import random
from datetime import datetime, timedelta

from faker import Faker

# ---- config -----------------------------------------------------------------
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 9, 30, 23, 59, 59)
N_USERS = 2000
N_MERCHANTS = 60
DEFAULT_ROWS = 100_000

fake = Faker("en_IN")

# lookup values ---------------------------------------------------------------
BANKS = [
    "HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank",
    "Kotak Mahindra Bank", "Punjab National Bank", "Yes Bank",
    "IDFC First Bank", "Bank of Baroda", "Canara Bank",
    "Union Bank of India", "IndusInd Bank",
]
# the bank we quietly make worse than the rest
PROBLEM_BANK = "IndusInd Bank"
SHAKY_BANKS = {"Yes Bank", "Punjab National Bank", "Union Bank of India"}

PAYMENT_MODES = ["UPI", "Credit Card", "Debit Card", "Net Banking", "Wallet"]

DEVICES = [
    ("Android", "14"), ("Android", "13"), ("Android", "11"), ("Android", "9"),
    ("iOS", "17"), ("iOS", "16"),
    ("Web", "Chrome"), ("Web", "Safari"),
]
OLD_ANDROID = ("Android", "9")

MERCHANT_CATEGORIES = [
    "E-commerce", "Food Delivery", "Utilities", "Travel",
    "Entertainment", "Education", "Healthcare", "Groceries",
]

FAILURE_REASONS = [
    "Insufficient Balance",
    "Bank Server Timeout",
    "Invalid OTP / Authentication Failed",
    "Payment Gateway Error",
    "Transaction Limit Exceeded",
    "User Cancelled",
    "Network Timeout",
]

# how big a typical transaction is, per mode (rupees). cards/netbanking skew high.
AMOUNT_RANGE = {
    "UPI": (10, 6000),
    "Wallet": (10, 3000),
    "Debit Card": (100, 25000),
    "Credit Card": (200, 60000),
    "Net Banking": (500, 90000),
}


def build_lookup_tables():
    users = []
    for uid in range(1, N_USERS + 1):
        signup = fake.date_between(start_date="-3y", end_date="today")
        users.append((uid, fake.name(), fake.city(), signup.isoformat()))

    banks = [(i + 1, name) for i, name in enumerate(BANKS)]
    modes = [(i + 1, name) for i, name in enumerate(PAYMENT_MODES)]
    devices = [(i + 1, dt, ver) for i, (dt, ver) in enumerate(DEVICES)]
    reasons = [(i + 1, txt) for i, txt in enumerate(FAILURE_REASONS)]

    merchants = []
    for mid in range(1, N_MERCHANTS + 1):
        name = fake.company()
        cat = random.choice(MERCHANT_CATEGORIES)
        merchants.append((mid, name, cat))

    return users, banks, modes, devices, merchants, reasons


def hour_weights():
    # more traffic in waking hours, quiet overnight. index = hour of day.
    w = []
    for h in range(24):
        if 0 <= h < 6:
            w.append(0.3)
        elif 6 <= h < 9:
            w.append(0.8)
        elif 9 <= h < 12:
            w.append(1.4)
        elif 12 <= h < 15:
            w.append(1.6)
        elif 15 <= h < 19:
            w.append(1.5)
        elif 19 <= h < 23:
            w.append(1.7)
        else:  # 23
            w.append(0.7)
    return w


def random_txn_time(hweights):
    # slight upward drift in volume over the 9 months so a growth trend shows up
    span_days = (END_DATE - START_DATE).days
    day_offset = int(random.triangular(0, span_days, span_days * 0.7))
    hour = random.choices(range(24), weights=hweights, k=1)[0]
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    day = START_DATE + timedelta(days=day_offset)
    return day.replace(hour=hour, minute=minute, second=second)


def failure_probability(bank_name, mode_name, device, hour):
    device_type, device_ver = device
    p = 0.055  # baseline failure

    if bank_name == PROBLEM_BANK:
        p *= 3.4
    elif bank_name in SHAKY_BANKS:
        p *= 1.35

    if hour in (0, 1, 2):          # overnight maintenance / load window
        p *= 2.3
    elif hour in (3, 4):
        p *= 1.4

    if (device_type, device_ver) == OLD_ANDROID:
        p *= 1.7
    elif device_type == "Android":
        p *= 1.12

    mode_mult = {
        "Net Banking": 1.5, "Wallet": 1.2, "Credit Card": 1.1,
        "Debit Card": 1.0, "UPI": 0.85,
    }
    p *= mode_mult[mode_name]

    # the nasty corner: bad bank + Android + dead of night compounds
    if bank_name == PROBLEM_BANK and device_type == "Android" and hour in (0, 1, 2):
        p *= 1.6

    return min(p, 0.9)


def pick_failure_reason(bank_name, mode_name, hour):
    weights = {r: 1.0 for r in FAILURE_REASONS}

    if bank_name == PROBLEM_BANK:
        weights["Bank Server Timeout"] += 4.0
        weights["Payment Gateway Error"] += 2.0
    if hour in (0, 1, 2, 3, 4):
        weights["Network Timeout"] += 2.5
        weights["Bank Server Timeout"] += 1.5
    if mode_name in ("Credit Card", "Debit Card"):
        weights["Insufficient Balance"] += 2.0
        weights["Invalid OTP / Authentication Failed"] += 1.5
    if mode_name == "Net Banking":
        weights["Invalid OTP / Authentication Failed"] += 1.5
    if mode_name == "UPI":
        weights["User Cancelled"] += 1.0

    reasons = list(weights.keys())
    return random.choices(reasons, weights=[weights[r] for r in reasons], k=1)[0]


def draw_amount(mode_name):
    lo, hi = AMOUNT_RANGE[mode_name]
    # lognormal-ish: most transactions small, long tail of big ones
    val = random.lognormvariate(mu=0.0, sigma=1.0)
    amount = lo + (hi - lo) * min(val / 6.0, 1.0)
    return round(amount, 2)


def build_transactions(n_rows, banks, modes, devices, merchants, reasons):
    hweights = hour_weights()
    reason_id_by_text = {txt: rid for rid, txt in reasons}

    rows = []
    for txn_id in range(1, n_rows + 1):
        user_id = random.randint(1, N_USERS)
        bank_id, bank_name = random.choice(banks)
        mode_id, mode_name = random.choice(modes)
        dev_id, dev_type, dev_ver = random.choice(devices)
        merch_id = random.choice(merchants)[0]

        ts = random_txn_time(hweights)
        amount = draw_amount(mode_name)

        p_fail = failure_probability(bank_name, mode_name, (dev_type, dev_ver), ts.hour)
        failed = random.random() < p_fail

        if failed:
            status = "FAILED"
            reason_text = pick_failure_reason(bank_name, mode_name, ts.hour)
            reason_id = reason_id_by_text[reason_text]
        else:
            status = "SUCCESS"
            reason_id = ""  # empty -> NULL on load

        rows.append((
            txn_id, user_id, bank_id, mode_id, dev_id, merch_id,
            amount, ts.strftime("%Y-%m-%d %H:%M:%S"), status, reason_id,
        ))
    return rows


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="Generate synthetic payment data.")
    ap.add_argument("--rows", type=int, default=DEFAULT_ROWS,
                    help="number of transactions to generate")
    ap.add_argument("--seed", type=int, default=91)
    args = ap.parse_args()

    random.seed(args.seed)
    Faker.seed(args.seed)

    os.makedirs(OUT_DIR, exist_ok=True)
    users, banks, modes, devices, merchants, reasons = build_lookup_tables()

    write_csv(os.path.join(OUT_DIR, "users.csv"),
              ["user_id", "name", "city", "signup_date"], users)
    write_csv(os.path.join(OUT_DIR, "banks.csv"),
              ["bank_id", "bank_name"], banks)
    write_csv(os.path.join(OUT_DIR, "payment_modes.csv"),
              ["mode_id", "mode_name"], modes)
    write_csv(os.path.join(OUT_DIR, "devices.csv"),
              ["device_id", "device_type", "os_version"], devices)
    write_csv(os.path.join(OUT_DIR, "merchants.csv"),
              ["merchant_id", "merchant_name", "category"], merchants)
    write_csv(os.path.join(OUT_DIR, "failure_reasons.csv"),
              ["reason_id", "reason_text"], reasons)

    txns = build_transactions(args.rows, banks, modes, devices, merchants, reasons)
    write_csv(
        os.path.join(OUT_DIR, "transactions.csv"),
        ["txn_id", "user_id", "bank_id", "mode_id", "device_id",
         "merchant_id", "amount", "txn_time", "status", "reason_id"],
        txns,
    )

    failed = sum(1 for r in txns if r[8] == "FAILED")
    print(f"wrote {len(txns):,} transactions to {OUT_DIR}")
    print(f"overall failure rate: {failed / len(txns) * 100:.2f}%")


if __name__ == "__main__":
    main()
