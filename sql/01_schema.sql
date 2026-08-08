-- Payment analytics schema: one fact table (transactions) surrounded by
-- six dimension/lookup tables. Star schema so the joins stay simple.
--
-- Run first, before loading data:  psql -d payments -f sql/01_schema.sql

DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS banks CASCADE;
DROP TABLE IF EXISTS payment_modes CASCADE;
DROP TABLE IF EXISTS devices CASCADE;
DROP TABLE IF EXISTS merchants CASCADE;
DROP TABLE IF EXISTS failure_reasons CASCADE;

CREATE TABLE users (
    user_id      INTEGER PRIMARY KEY,
    name         VARCHAR(120) NOT NULL,
    city         VARCHAR(80),
    signup_date  DATE
);

CREATE TABLE banks (
    bank_id      INTEGER PRIMARY KEY,
    bank_name    VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE payment_modes (
    mode_id      INTEGER PRIMARY KEY,
    mode_name    VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE devices (
    device_id    INTEGER PRIMARY KEY,
    device_type  VARCHAR(20) NOT NULL,   -- Android / iOS / Web
    os_version   VARCHAR(20)
);

CREATE TABLE merchants (
    merchant_id  INTEGER PRIMARY KEY,
    merchant_name VARCHAR(120) NOT NULL,
    category     VARCHAR(40)
);

CREATE TABLE failure_reasons (
    reason_id    INTEGER PRIMARY KEY,
    reason_text  VARCHAR(80) NOT NULL
);

CREATE TABLE transactions (
    txn_id       BIGINT PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(user_id),
    bank_id      INTEGER NOT NULL REFERENCES banks(bank_id),
    mode_id      INTEGER NOT NULL REFERENCES payment_modes(mode_id),
    device_id    INTEGER NOT NULL REFERENCES devices(device_id),
    merchant_id  INTEGER NOT NULL REFERENCES merchants(merchant_id),
    amount       NUMERIC(12, 2) NOT NULL,
    txn_time     TIMESTAMP NOT NULL,
    status       VARCHAR(10) NOT NULL CHECK (status IN ('SUCCESS', 'FAILED')),
    reason_id    INTEGER REFERENCES failure_reasons(reason_id)  -- NULL when SUCCESS
);

-- indexes on the columns we filter / group by the most
CREATE INDEX idx_txn_status  ON transactions (status);
CREATE INDEX idx_txn_bank    ON transactions (bank_id);
CREATE INDEX idx_txn_mode    ON transactions (mode_id);
CREATE INDEX idx_txn_time    ON transactions (txn_time);
