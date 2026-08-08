-- =============================================================
-- Payment failure analysis
-- Each query answers one question. Run them individually.
--   psql -d payments -f sql/02_analysis.sql
-- =============================================================


-- 1. Headline numbers: overall success vs failure, and money left on the table
SELECT
    status,
    COUNT(*)                                                   AS txns,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2)         AS pct_of_total,
    ROUND(SUM(amount), 2)                                      AS total_amount
FROM transactions
GROUP BY status
ORDER BY txns DESC;


-- 2. Failure rate by bank, with the rupee value of failed transactions.
--    This is where the worst offender first shows up.
SELECT
    b.bank_name,
    COUNT(*)                                                       AS total_txns,
    COUNT(*) FILTER (WHERE t.status = 'FAILED')                    AS failed_txns,
    ROUND(COUNT(*) FILTER (WHERE t.status = 'FAILED') * 100.0
          / COUNT(*), 2)                                           AS failure_rate_pct,
    ROUND(SUM(t.amount) FILTER (WHERE t.status = 'FAILED'), 2)     AS revenue_lost
FROM transactions t
JOIN banks b ON t.bank_id = b.bank_id
GROUP BY b.bank_name
ORDER BY failure_rate_pct DESC;


-- 3. Failure rate by payment mode
SELECT
    pm.mode_name,
    COUNT(*)                                                   AS total_txns,
    ROUND(COUNT(*) FILTER (WHERE t.status = 'FAILED') * 100.0
          / COUNT(*), 2)                                       AS failure_rate_pct
FROM transactions t
JOIN payment_modes pm ON t.mode_id = pm.mode_id
GROUP BY pm.mode_name
ORDER BY failure_rate_pct DESC;


-- 4. Failure rate by device (type + OS version). Old Android should stand out.
SELECT
    d.device_type,
    d.os_version,
    COUNT(*)                                                   AS total_txns,
    ROUND(COUNT(*) FILTER (WHERE t.status = 'FAILED') * 100.0
          / COUNT(*), 2)                                       AS failure_rate_pct
FROM transactions t
JOIN devices d ON t.device_id = d.device_id
GROUP BY d.device_type, d.os_version
ORDER BY failure_rate_pct DESC;


-- 5. Failure rate by hour of day. Looking for a time-of-day cluster.
SELECT
    EXTRACT(HOUR FROM txn_time)::INT                           AS hour_of_day,
    COUNT(*)                                                   AS total_txns,
    ROUND(COUNT(*) FILTER (WHERE status = 'FAILED') * 100.0
          / COUNT(*), 2)                                       AS failure_rate_pct
FROM transactions
GROUP BY hour_of_day
ORDER BY hour_of_day;


-- 6. Hour x weekday grid — feeds the dashboard heatmap.
SELECT
    EXTRACT(HOUR FROM txn_time)::INT                           AS hour_of_day,
    TO_CHAR(txn_time, 'Dy')                                    AS weekday,
    ROUND(COUNT(*) FILTER (WHERE status = 'FAILED') * 100.0
          / COUNT(*), 2)                                       AS failure_rate_pct
FROM transactions
GROUP BY hour_of_day, weekday
ORDER BY hour_of_day;


-- 7. ROOT CAUSE: worst bank x payment-mode combinations.
--    HAVING guards against tiny buckets giving a misleading 100%.
SELECT
    b.bank_name,
    pm.mode_name,
    COUNT(*)                                                   AS total_txns,
    ROUND(COUNT(*) FILTER (WHERE t.status = 'FAILED') * 100.0
          / COUNT(*), 2)                                       AS failure_rate_pct
FROM transactions t
JOIN banks b          ON t.bank_id = b.bank_id
JOIN payment_modes pm ON t.mode_id = pm.mode_id
GROUP BY b.bank_name, pm.mode_name
HAVING COUNT(*) > 50
ORDER BY failure_rate_pct DESC
LIMIT 10;


-- 8. ROOT CAUSE: worst bank x device combinations.
SELECT
    b.bank_name,
    d.device_type,
    d.os_version,
    COUNT(*)                                                   AS total_txns,
    ROUND(COUNT(*) FILTER (WHERE t.status = 'FAILED') * 100.0
          / COUNT(*), 2)                                       AS failure_rate_pct
FROM transactions t
JOIN banks b   ON t.bank_id = b.bank_id
JOIN devices d ON t.device_id = d.device_id
GROUP BY b.bank_name, d.device_type, d.os_version
HAVING COUNT(*) > 50
ORDER BY failure_rate_pct DESC
LIMIT 10;


-- 9. Isolate the specific pocket: worst bank, on Android, in the 0-3am window,
--    vs everything else. Quantifies just how bad that corner is.
SELECT
    CASE
        WHEN b.bank_name = 'IndusInd Bank'
             AND d.device_type = 'Android'
             AND EXTRACT(HOUR FROM t.txn_time) IN (0, 1, 2)
        THEN 'IndusInd + Android + 12-3am'
        ELSE 'Everything else'
    END                                                        AS segment,
    COUNT(*)                                                   AS total_txns,
    ROUND(COUNT(*) FILTER (WHERE t.status = 'FAILED') * 100.0
          / COUNT(*), 2)                                       AS failure_rate_pct,
    ROUND(SUM(t.amount) FILTER (WHERE t.status = 'FAILED'), 2) AS revenue_lost
FROM transactions t
JOIN banks b   ON t.bank_id = b.bank_id
JOIN devices d ON t.device_id = d.device_id
GROUP BY segment;


-- 10. Month-over-month failure-rate trend using LAG() to compare with prior month.
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', txn_time)::DATE                    AS month,
        COUNT(*)                                              AS total_txns,
        ROUND(COUNT(*) FILTER (WHERE status = 'FAILED') * 100.0
              / COUNT(*), 2)                                  AS failure_rate_pct
    FROM transactions
    GROUP BY month
)
SELECT
    month,
    total_txns,
    failure_rate_pct,
    LAG(failure_rate_pct) OVER (ORDER BY month)               AS prev_month_pct,
    ROUND(failure_rate_pct
          - LAG(failure_rate_pct) OVER (ORDER BY month), 2)   AS change_pct_pts
FROM monthly
ORDER BY month;


-- 11. Which reasons actually drive the failures?
SELECT
    fr.reason_text,
    COUNT(*)                                                   AS occurrences,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2)         AS pct_of_failures
FROM transactions t
JOIN failure_reasons fr ON t.reason_id = fr.reason_id
WHERE t.status = 'FAILED'
GROUP BY fr.reason_text
ORDER BY occurrences DESC;
