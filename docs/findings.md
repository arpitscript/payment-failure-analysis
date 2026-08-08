# Findings

Analysis of 100,000 synthetic payment transactions (Jan–Sep 2025) to find where
payments fail and what those failures cost.

## Headline

- Overall failure rate: **9.52%** (9,519 of 100,000 transactions failed).
- Value of failed transactions: **₹10.21 Cr** — money that customers tried to
  spend but couldn't.
- The failures are not spread evenly. They cluster hard around one bank, one
  time window, and older Android clients, and these effects compound.

## 1. One bank drives most of the pain

| Bank | Failure rate | Value failed |
|------|-------------:|-------------:|
| IndusInd Bank | **24.98%** | ₹2.17 Cr |
| Yes Bank | 10.32% | ₹0.93 Cr |
| Punjab National Bank | 10.17% | ₹0.88 Cr |
| … | … | … |
| HDFC Bank (best) | 6.98% | ₹0.66 Cr |

IndusInd fails **~3.5x** more often than the healthiest banks and alone accounts
for roughly a fifth of all lost transaction value.

## 2. Failures spike overnight

Failure rate by hour is flat (~8–9%) through the day, then jumps in the
12am–3am window:

- 12am: 22.2% · 1am: 20.1% · 2am: 21.6%
- 3–4am still elevated (~13%) before settling back down.

This looks like a server/maintenance load window rather than a customer problem.

## 3. Old Android clients fail more

| Device | Failure rate |
|--------|-------------:|
| Android 9 (old build) | **14.47%** |
| Android 11/13/14 | ~9.3% |
| iOS 16/17 | ~8.1–8.6% |

## 4. Payment mode matters

Net Banking (12.58%) and Wallet (10.20%) are the weakest rails; UPI is the
healthiest at 7.31%.

## 5. The root cause — where the effects stack

Slicing by bank × mode and bank × device surfaces the real problem pocket:

- **IndusInd × Net Banking: 32.83%** failure.
- **IndusInd Bank + Android + 12–3am: 76.06%** failure across 142 transactions,
  ₹11.15 L in failed value — versus **9.42%** for everything else on the platform.

That single corner of the data fails three out of four times. It's a specific,
fixable target, not a vague "improve reliability."

## 6. Why transactions fail

Top reasons among failed transactions: Invalid OTP / Auth (18.7%),
Insufficient Balance (17.1%), Bank Server Timeout (17.0%). The timeout share is
inflated inside the IndusInd/overnight pocket, consistent with an
infrastructure issue on that bank's side.

## Recommendation

Treat the IndusInd overnight path as an incident, not a metric. Two concrete moves:

1. Add a fallback gateway/retry for IndusInd Net Banking transactions during the
   12am–3am window — that pocket alone is losing ~₹11 L on a tiny slice of volume.
2. Prompt users on the old Android build to update, or ship a compatibility fix,
   since that client fails ~5 points above the app average.

---

*Data is synthetic. The bank/time/device patterns above were deliberately
injected during generation so there would be something real to find; they do not
describe any actual institution's reliability.*
