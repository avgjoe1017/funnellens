# FunnelLens v1.0 → v1.1 Changelog
**Critical fixes from stress test feedback**

---

## What Was Broken (and How We Fixed It)

### 1. View Attribution Was Fundamentally Wrong

**Problem:** CSV exports give cumulative views (total lifetime views). If a post has 500K views total but only gained 2K views during your attribution window, your "subs per 1K views" metric was using the wrong denominator.

**Fix:** Added `PostSnapshot` table to store point-in-time metrics. Each CSV import creates a snapshot. Delta calculation:

```
views_during_window = snapshot_end.views - snapshot_start.views
```

This is the single most important fix. Without it, every metric was wrong.

---

### 2. Baseline Included the Push Period

**Problem:** The baseline calculation ended at `window_end`, which means if you're measuring a "storytime week," your baseline already includes some of that week's data. The lift is contaminated.

**Before:**
```python
# WRONG: baseline_end could be after window_start
baseline_end = now - exclude_days
```

**After:**
```python
# CORRECT: baseline strictly before the window
baseline = calculate_baseline(
    creator_id,
    baseline_end=window_start,  # Ends where window begins
    lookback_days=14
)
```

---

### 3. Window Duration Truncated to Zero

**Problem:** `(window_end - window_start).days` uses integer division. A 36-hour window = 1 day. A 20-hour window = 0 days → expected_subs = 0 → lift = infinity.

**Fix:** Use hours with minimum threshold:

```python
window_hours = (window_end - window_start).total_seconds() / 3600
window_hours = max(window_hours, 1)  # Minimum 1 hour
```

---

### 4. Confidence Score Was Backwards

**Problem:** Confidence was based on number of posts, not number of subs. A creator with 50 posts but only 3 subs would show "high confidence." That's exactly wrong.

**Fix:** New `ConfidenceScorer` class uses event counts:

```python
MIN_SUBS_FOR_RECOMMENDATION = 10
MIN_SUBS_FOR_CONFIDENT = 25

if actual_events < MIN_SUBS_FOR_RECOMMENDATION:
    score -= 0.3
    min_events_met = False
```

Also added proper Poisson test for statistical significance.

---

### 5. Reach Bias (Thirst Traps Stealing Credit)

**Problem:** When a storytime and thirst-trap posted the same day, the higher-view content (thirst-trap) stole all attribution credit—even if the storytime actually drove the conversion.

**Fix:** Weighted credit split based on view delta share:

```python
# Instead of winner-takes-all
weights = {}
for ct, data in content_deltas.items():
    weights[ct] = data["views_delta"] / total_views

fan.attribution_weights = {"storytime": 0.6, "thirst_trap": 0.4}
```

Primary attribution goes to highest weight, but the split is recorded.

---

### 6. No Confounder Awareness

**Problem:** Price changes, collabs, Reddit threads, OF promos all create lift that gets mis-attributed to content.

**Fix:** Added `ConfounderEvent` model:

```python
class ConfounderEvent(Base):
    event_type = Column(Enum(
        "price_change", "promotion", "collab", 
        "external_traffic", "mass_dm", "of_promo"
    ))
    event_start = Column(DateTime)
    event_end = Column(DateTime)
```

Recommendations are flagged when confounders overlap:

```
⚠️ Confounder event(s) overlap with window
```

---

### 7. All Recommendations Looked Equal

**Problem:** A recommendation backed by 50 subs and one backed by 8 subs both said "Post more storytime."

**Fix:** Two-tier output system:

- **CONFIDENT**: High confidence (≥25 subs, ≥0.7 confidence score). Act on it.
- **HYPOTHESIS**: Lower confidence (10-24 subs or <0.7 score). Worth testing.

The Monday email now gates strong claims on confidence level.

---

### 8. Fan ID Hashing Wasn't Salted

**Problem:** Same fan ID across different agencies would hash to the same value, enabling cross-agency tracking (TOS violation).

**Fix:** Per-agency salt:

```python
class Agency(Base):
    fan_id_salt = Column(String(64), default=lambda: secrets.token_hex(32))

# During import:
hash = hashlib.sha256((fan_id + agency.fan_id_salt).encode()).hexdigest()
```

---

## New Validation Requirements

Before shipping, run these tests:

### Backtest Accuracy
Compare weighted attribution vs referral-link ground truth. Target: >60% match.

### Placebo Test
Run attribution on random windows with no content. Target: <20% false positive rate.

### Lag Sensitivity
Test 24h/48h/72h/7d windows per creator. If rankings flip wildly, extend baseline or downgrade outputs.

---

## What We Didn't Change

These concerns were valid but not v1 blockers:

- **Database bloat**: TimescaleDB handles this at year-1 scale. Premature optimization.
- **API access**: Already planned for v1.5. CSV-first is correct.
- **CRM competition**: True, but you ship to find out. Moat is cross-agency benchmarks.
- **Payment processing**: Operational risk, not spec-level.

---

## Files

- `funnellens-v1-spec.md` — Original 1-page product spec (still valid)
- `funnellens-technical-spec.md` — Original technical spec (v1.0)
- `funnellens-technical-spec-v1.1.md` — **Revised spec with critical fixes**

Use v1.1 for implementation.
