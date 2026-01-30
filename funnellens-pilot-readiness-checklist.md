# FunnelLens Pilot Readiness Checklist
**Pass/Fail criteria before scaling beyond 3 pilot agencies**

---

## Overview

This checklist validates that FunnelLens can deliver on its core promise without destroying trust. Run these tests on your first 3 pilot agencies before:
- Turning on paid subscriptions
- Sending the Monday email automatically
- Making "confident" recommendations without manual review

**Philosophy:** A measurement product that's wrong-but-confident is worse than no product. These gates ensure you know what you don't know.

---

## Section 1: Measurement Accuracy

### 1.1 Calibration Backtest (Ground Truth)

**What:** Compare FunnelLens attribution vs referral-link-attributed subs.

**Why:** Referral links are deterministic. If your probabilistic model can't roughly match them, you're guessing.

**How to run:**
```python
# For each pilot agency
for creator in agency.creators:
    result = backtest_attribution_accuracy(creator.id)
    log(f"{creator.name}: {result['accuracy']:.0%} match, n={result['sample_size']}")
```

**Pass criteria:**

| Metric | Pass | Fail |
|--------|------|------|
| Overall accuracy | ≥60% | <50% |
| Per-creator minimum | ≥40% for all | Any creator <30% |
| Sample size | ≥20 referral-link subs | <10 (insufficient data) |

**If you fail:**
- Increase attribution window (48h → 72h)
- Check if referral links are tagged with content_type_hint
- Verify snapshot deltas are computing correctly

**Evidence to record:**
```
□ Backtest run date: ___________
□ Agencies tested: ___________
□ Overall accuracy: ___________
□ Worst-performing creator: ___________ (accuracy: ____)
□ PASS / FAIL
```

---

### 1.2 Placebo Test (False Positive Rate)

**What:** Run attribution on random windows with no significant content pushes.

**Why:** If you see lift when nothing happened, your baseline/seasonality model is broken.

**How to run:**
```python
for creator in agency.creators:
    result = placebo_test(creator.id, n_tests=10)
    log(f"{creator.name}: {result['false_positive_rate']:.0%} FP rate")
```

**Pass criteria:**

| Metric | Pass | Fail |
|--------|------|------|
| False positive rate | <20% | ≥30% |
| Any "confident" false positive | 0 | ≥1 |

**If you fail:**
- Check baseline window isn't contaminated
- Add day-of-week adjustment
- Verify you're using delta views, not cumulative

**Evidence to record:**
```
□ Placebo test run date: ___________
□ Total tests run: ___________
□ False positives: ___________
□ Any "confident" false positives: YES / NO
□ PASS / FAIL
```

---

### 1.3 Lag Sensitivity Test

**What:** Compute content-type rankings using 24h, 48h, 72h, and 7d attribution windows.

**Why:** If rankings flip wildly across windows, your recommendations are unstable.

**How to run:**
```python
for creator in agency.creators:
    rankings = {}
    for hours in [24, 48, 72, 168]:
        result = get_content_type_rankings(creator.id, window_hours=hours)
        rankings[hours] = result['ranking_order']  # e.g., ["storytime", "grwm", "thirst_trap"]
    
    stability = compute_ranking_stability(rankings)  # Kendall's tau or simple overlap
    log(f"{creator.name}: stability={stability:.2f}")
```

**Pass criteria:**

| Metric | Pass | Fail |
|--------|------|------|
| Ranking stability (Kendall's τ) | ≥0.6 avg | <0.4 avg |
| Top recommendation same across windows | ≥70% of creators | <50% of creators |

**If you fail:**
- Implement per-creator optimal window learning
- Downgrade all outputs to "hypothesis" tier until stable
- Consider longer baseline period

**Evidence to record:**
```
□ Lag test run date: ___________
□ Average stability score: ___________
□ Creators with stable top recommendation: ___/___
□ PASS / FAIL
```

---

## Section 2: Operational Workflow

### 2.1 Time to First Insight

**What:** Measure wall-clock time from "agency signs up" to "first actionable recommendation displayed."

**Why:** Your success metric is "answer within 5 minutes of first import." If onboarding takes 45 minutes, you'll churn.

**How to run:**
1. Fresh agency account (no prior data)
2. Provide sample CSV exports from their actual CRM/social tools
3. Start timer when they click "Import"
4. Stop timer when first recommendation appears on dashboard

**Pass criteria:**

| Metric | Pass | Fail |
|--------|------|------|
| Time to first insight | <15 minutes | >30 minutes |
| CSV import success rate | >90% first attempt | <70% first attempt |
| Mapping wizard completion | <5 minutes | >10 minutes |

**If you fail:**
- Build "golden path" templates for top 3 CRMs (FansMetric, FansCRM, OF native)
- Add better error messages on validation failures
- Pre-populate common column mappings

**Evidence to record:**
```
□ Test run date: ___________
□ Time to first insight: ___________ minutes
□ Import attempts needed: ___________
□ Mapping wizard time: ___________ minutes
□ PASS / FAIL
```

---

### 2.2 Weekly Workflow Burden

**What:** Measure time for weekly maintenance (CSV upload + tagging) per creator.

**Why:** You're targeting ~2 min/creator/week. If it's 10 min/creator, agencies with 30 creators won't stick.

**How to run:**
1. Simulate week 2+ workflow (not onboarding)
2. Time: CSV export from CRM → upload → CSV export from TikTok → upload → tag queue → done
3. Repeat for 5 creators

**Pass criteria:**

| Metric | Pass | Fail |
|--------|------|------|
| Per-creator weekly time | <5 minutes | >10 minutes |
| Tagging queue time | <2 minutes | >5 minutes |
| ML suggestion acceptance rate | >70% | <50% |

**If you fail:**
- Improve ML classifier (more training data, better prompts)
- Add "Accept All Suggested" batch action
- Reduce to "Top 10" posts instead of Top 20

**Evidence to record:**
```
□ Test run date: ___________
□ Average per-creator time: ___________ minutes
□ Tagging queue time: ___________ minutes
□ ML acceptance rate: ___________%
□ PASS / FAIL
```

---

## Section 3: Trust & Uncertainty UX

### 3.1 Confounder Coverage

**What:** Verify confounder events are being logged and affecting outputs.

**Why:** If confounders aren't logged, you'll make confident claims during sale weeks.

**How to run:**
1. Check each pilot creator has ≥1 confounder event logged
2. Verify that recommendations during confounder windows show warning badge
3. Verify that confidence scores are reduced when confounders overlap

**Pass criteria:**

| Metric | Pass | Fail |
|--------|------|------|
| Confounder events logged | ≥1 per creator | 0 for any creator |
| Warning badge displays | 100% when overlap | Missing on any overlap |
| Confidence reduction | ≥0.2 score reduction | No reduction |

**If you fail:**
- Make confounder log part of onboarding flow
- Add "Did anything unusual happen this week?" prompt on import
- Hard-block "confident" tier when confounders present

**Evidence to record:**
```
□ Test run date: ___________
□ Creators with confounders logged: ___/___
□ Warning badges displaying correctly: YES / NO
□ Confidence reduction working: YES / NO
□ PASS / FAIL
```

---

### 3.2 Two-Tier Output Separation

**What:** Verify "Confident" and "Hypothesis" recommendations are clearly distinguished.

**Why:** If all recommendations look the same, agencies will act on weak signals.

**How to run:**
1. Generate recommendations for all pilot creators
2. Check that "Confident" requires: ≥25 subs AND ≥0.7 confidence AND no confounders
3. Check that "Hypothesis" uses softer language ("worth testing" not "do this")
4. Check that insufficient data shows "Building baseline" not fake recommendations

**Pass criteria:**

| Metric | Pass | Fail |
|--------|------|------|
| Confident threshold enforced | 100% | Any violation |
| Language differentiation | Clear distinction | Similar phrasing |
| Insufficient data handling | Shows diagnostic | Shows fake recommendation |

**If you fail:**
- Audit recommendation engine thresholds
- Rewrite copy for each tier
- Add explicit "confidence: high/medium/low" label in UI

**Evidence to record:**
```
□ Test run date: ___________
□ Confident threshold violations: ___________
□ Language clearly differentiated: YES / NO
□ Insufficient data handled correctly: YES / NO
□ PASS / FAIL
```

---

### 3.3 Monday Email Gating

**What:** Verify the Monday email doesn't make strong claims on weak data.

**Why:** The email is the most visible surface. Errors here get forwarded and amplified.

**How to run:**
1. Generate Monday email for all pilot creators
2. Check that "Best Performer" only appears when confidence ≥ threshold
3. Check that confounder warnings appear when relevant
4. Check that low-confidence weeks use softer framing ("Patterns to test" not "Clear wins")

**Pass criteria:**

| Metric | Pass | Fail |
|--------|------|------|
| Strong claims on low confidence | 0 | Any |
| Confounder warnings included | 100% when relevant | Missing any |
| Email type matches confidence | 100% | Any mismatch |

**If you fail:**
- Hard-code confidence gates in email generation
- Add manual review step before auto-send (for pilots)
- Consider not auto-sending until gate passes

**Evidence to record:**
```
□ Test run date: ___________
□ Emails reviewed: ___________
□ Inappropriate strong claims: ___________
□ Missing confounder warnings: ___________
□ PASS / FAIL
```

---

## Section 4: Data Quality

### 4.1 Snapshot Coverage

**What:** Verify snapshot/delta system is working correctly.

**Why:** Without snapshots, view deltas can't be computed, and attribution is broken.

**How to run:**
1. For each creator, check that posts have ≥2 snapshots (needed for delta)
2. Verify delta calculation: `views_delta = snapshot_2.views - snapshot_1.views`
3. Check for negative deltas (indicates data error)

**Pass criteria:**

| Metric | Pass | Fail |
|--------|------|------|
| Posts with ≥2 snapshots | >80% | <60% |
| Negative deltas | 0 | Any |
| Snapshot coverage period | ≥14 days | <7 days |

**If you fail:**
- Ensure every import creates snapshots
- Backfill historical snapshots if possible
- Block attribution for posts without sufficient snapshots

**Evidence to record:**
```
□ Test run date: ___________
□ Posts with ≥2 snapshots: ___________%
□ Negative deltas found: ___________
□ Snapshot coverage: ___________ days
□ PASS / FAIL
```

---

### 4.2 Baseline Data Sufficiency

**What:** Verify baseline calculation has enough data to be meaningful.

**Why:** A 3-day baseline is noise, not signal.

**How to run:**
1. For each creator, check `baseline.data_days`
2. Verify baseline isn't using defaults (`is_default: false`)
3. Check day-of-week factors are computed (not all 1.0)

**Pass criteria:**

| Metric | Pass | Fail |
|--------|------|------|
| Baseline data days | ≥10 avg | <7 avg |
| Using default baseline | <20% of creators | >40% of creators |
| DOW factors computed | >80% of creators | <50% of creators |

**If you fail:**
- Require longer history before showing recommendations
- Show "Insufficient baseline" instead of fake outputs
- Import more historical data

**Evidence to record:**
```
□ Test run date: ___________
□ Average baseline days: ___________
□ Creators using default baseline: ___/___
□ Creators with DOW factors: ___/___
□ PASS / FAIL
```

---

## Section 5: Agency Sanity Check

### 5.1 "Does This Match Reality?" Interview

**What:** Ask pilot agencies if FunnelLens outputs match their intuition.

**Why:** Agencies have ground truth you can't measure. If outputs feel wrong, trust is gone.

**How to run:**
1. Show agency the content-type performance table
2. Ask: "Does this match what you've observed?"
3. Ask: "Any recommendations that surprise you (in a bad way)?"
4. Ask: "Would you forward this Monday email to a creator?"

**Pass criteria:**

| Metric | Pass | Fail |
|--------|------|------|
| "Matches intuition" | ≥2/3 agencies | 0/3 agencies |
| Surprising bad recommendations | ≤1 per agency | >3 per agency |
| Would forward email | ≥2/3 agencies | 0/3 agencies |

**If you fail:**
- Dig into specific disagreements
- Check for confounder events not logged
- Consider that you might be right and they might be wrong (but tread carefully)

**Evidence to record:**
```
□ Interview date: ___________
□ Agency 1: Matches intuition? Y/N | Bad surprises: ___ | Would forward? Y/N
□ Agency 2: Matches intuition? Y/N | Bad surprises: ___ | Would forward? Y/N
□ Agency 3: Matches intuition? Y/N | Bad surprises: ___ | Would forward? Y/N
□ PASS / FAIL
```

---

## Summary Scorecard

| Section | Test | Pass? |
|---------|------|-------|
| **1. Accuracy** | 1.1 Calibration Backtest | □ |
| | 1.2 Placebo Test | □ |
| | 1.3 Lag Sensitivity | □ |
| **2. Workflow** | 2.1 Time to First Insight | □ |
| | 2.2 Weekly Workflow Burden | □ |
| **3. Trust UX** | 3.1 Confounder Coverage | □ |
| | 3.2 Two-Tier Output Separation | □ |
| | 3.3 Monday Email Gating | □ |
| **4. Data Quality** | 4.1 Snapshot Coverage | □ |
| | 4.2 Baseline Data Sufficiency | □ |
| **5. Sanity Check** | 5.1 Agency Interview | □ |

---

## Go / No-Go Decision

### GREEN LIGHT (Scale to paid)
- All Section 1 tests pass
- All Section 3 tests pass
- ≥4/5 other tests pass
- Agency sanity check passes

### YELLOW LIGHT (Continue pilots with caveats)
- All Section 1 tests pass
- ≥2/3 Section 3 tests pass
- Known gaps documented and communicated to pilot agencies

### RED LIGHT (Do not scale)
- Any Section 1 test fails
- ≥2 Section 3 tests fail
- Agency sanity check fails

---

## Appendix: Test Implementation Code

### A.1 Backtest Function

```python
def backtest_attribution_accuracy(creator_id: UUID) -> Dict:
    """Compare probabilistic attribution vs referral-link ground truth."""
    db = get_db()
    snapshot_mgr = SnapshotManager(db)
    
    # Get fans with referral link attribution (ground truth)
    link_fans = db.query(Fan).filter(
        Fan.creator_id == creator_id,
        Fan.attribution_method == "referral_link",
        Fan.attributed_content_type.isnot(None)
    ).all()
    
    if len(link_fans) < 10:
        return {"accuracy": None, "sample_size": len(link_fans), "error": "insufficient_data"}
    
    matches = 0
    errors = []
    
    for fan in link_fans:
        actual_type = fan.attributed_content_type
        
        # What would weighted-window attribution have said?
        window_start = fan.acquired_at - timedelta(hours=48)
        deltas = snapshot_mgr.get_content_type_deltas(
            creator_id, window_start, fan.acquired_at
        )
        
        if not deltas:
            continue
        
        # Predicted = highest view-delta content type
        predicted_type = max(deltas, key=lambda ct: deltas[ct]["views_delta"])
        
        if actual_type == predicted_type:
            matches += 1
        else:
            errors.append({
                "fan_id": fan.id,
                "actual": actual_type,
                "predicted": predicted_type,
                "acquired_at": fan.acquired_at
            })
    
    total = len(link_fans)
    accuracy = matches / total if total > 0 else 0
    
    return {
        "accuracy": accuracy,
        "sample_size": total,
        "matches": matches,
        "errors": errors[:10],  # First 10 for debugging
        "confusion_matrix": build_confusion_matrix(link_fans, errors)
    }
```

### A.2 Placebo Test Function

```python
def placebo_test(creator_id: UUID, n_tests: int = 10) -> Dict:
    """Run attribution on random quiet windows to detect false positives."""
    db = get_db()
    attribution_svc = AttributionService(db)
    
    false_positives = []
    tests_run = 0
    
    for _ in range(n_tests * 3):  # Try more to find enough placebo windows
        if tests_run >= n_tests:
            break
        
        # Random window in last 90 days
        days_ago = random.randint(14, 90)
        window_end = datetime.utcnow() - timedelta(days=days_ago)
        window_start = window_end - timedelta(days=7)
        
        # Check if this is actually a quiet period
        posts_in_window = db.query(SocialPost).filter(
            SocialPost.creator_id == creator_id,
            SocialPost.posted_at >= window_start,
            SocialPost.posted_at < window_end,
            SocialPost.views_cumulative > 10000  # Significant posts only
        ).count()
        
        if posts_in_window > 3:
            continue  # Not a placebo window
        
        tests_run += 1
        
        # Run attribution
        result = attribution_svc.attribute_window(creator_id, window_start, window_end)
        
        # Check for false positive
        is_fp = (
            abs(result["subs_lift_pct"]) > 50 and 
            result["confidence"]["score"] > 0.5
        )
        
        if is_fp:
            false_positives.append({
                "window_start": window_start,
                "window_end": window_end,
                "lift_pct": result["subs_lift_pct"],
                "confidence": result["confidence"]["score"],
                "tier": result["recommendation_tier"]
            })
    
    return {
        "tests_run": tests_run,
        "false_positives": len(false_positives),
        "false_positive_rate": len(false_positives) / tests_run if tests_run > 0 else 0,
        "confident_fps": len([fp for fp in false_positives if fp["tier"] == "confident"]),
        "details": false_positives
    }
```

### A.3 Lag Sensitivity Function

```python
def lag_sensitivity_test(creator_id: UUID) -> Dict:
    """Test ranking stability across different attribution windows."""
    from scipy.stats import kendalltau
    
    db = get_db()
    windows = [24, 48, 72, 168]  # hours
    
    rankings = {}
    
    for hours in windows:
        # Get last 30 days of data with this window
        window_end = datetime.utcnow()
        window_start = window_end - timedelta(days=30)
        
        # Compute content-type performance
        performance = compute_content_type_performance(
            db, creator_id, window_start, window_end, 
            attribution_window_hours=hours
        )
        
        # Rank by lift
        ranked = sorted(
            performance.items(),
            key=lambda x: x[1].get("lift_pct", 0),
            reverse=True
        )
        rankings[hours] = [ct for ct, _ in ranked if ct != "other"]
    
    # Compute pairwise Kendall's tau
    taus = []
    for i, w1 in enumerate(windows):
        for w2 in windows[i+1:]:
            r1 = rankings[w1]
            r2 = rankings[w2]
            
            # Convert to numeric ranks
            rank1 = [r1.index(ct) if ct in r1 else len(r1) for ct in set(r1 + r2)]
            rank2 = [r2.index(ct) if ct in r2 else len(r2) for ct in set(r1 + r2)]
            
            tau, _ = kendalltau(rank1, rank2)
            taus.append(tau)
    
    avg_tau = sum(taus) / len(taus) if taus else 0
    
    # Check if top recommendation is stable
    top_recs = [rankings[w][0] if rankings[w] else None for w in windows]
    top_stable = len(set(top_recs)) == 1
    
    return {
        "rankings_by_window": rankings,
        "kendall_taus": taus,
        "average_tau": avg_tau,
        "top_recommendation_stable": top_stable,
        "stability_level": "high" if avg_tau >= 0.6 else "medium" if avg_tau >= 0.4 else "low"
    }
```

---

*Checklist version 1.0 — Run before scaling beyond pilot*
