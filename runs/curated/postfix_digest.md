# Failure digest

trials=['t0', 't1', 't2']  judge=on  memory=on
failures=9  infra_errors=0  total_runs=54

## Graded failures (read the transcript; do not auto-fix)
- **D-0006** [deny] trial=t1
    - action_correct: drafted='approve' expected='deny'
    - judge/consistent: Promo period ends 2025-10-27, so the claimed weeks (11/03–11/17) are outside the promotional window per §2.3, contradicting the justification's in-period claim; also funding cap is $8,000 and the promo is named 'October' Scandown, not covering November.
    - judge/dispute_proof: The claimed weeks (11/03–11/17) fall entirely outside the promo's stated period (ends 2025-10-27), violating §2.3, and exceed the $8,000 funding cap—the justification's core validity claims contradict the cited evidence, leaving obvious openings for dispute.
    - judge/no_unsupported: Claims the promo end date is 10/27 yet approves 11/03–11/17 scans as in-window; the evidence shows the promo period ended 2025-10-27, so the POS 'in-period' reconciliation and window compliance are unsupported/contradicted, and the $8,000 funding cap is ignored.
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t1/D-0006/record.json
- **D-0011** [partial] trial=t0
    - amount_within_tolerance: drafted=2045 expected=4000.0 |delta|=1955.00 allowed=40.00
    - judge/dispute_proof: The justification relies on ValuMax's ad proof and POS scan data establishing only two eligible feature weeks (2,045 units), but neither the ad proof nor the POS data is in the cited source evidence, leaving the ineligible-units determination unsupported and open to dispute.
    - judge/no_unsupported: The POS scan data (1,030+1,015 units) and the ad proof establishing only two feature weeks are cited as fact but appear in neither cited evidence item, making key figures unsupported.
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t0/D-0011/record.json
- **D-0011** [partial] trial=t2
    - amount_within_tolerance: drafted=2045 expected=4000.0 |delta|=1955.00 allowed=40.00
    - judge/consistent: The justification cites POS scan data and ad-proof attachment (1,030 and 1,015 units for specific feature weeks), but none of these are in the provided evidence — the cited evidence contains no POS data or ad proofs, so the 2,045-unit figure cannot be reconciled with what is shown.
    - judge/dispute_proof: The rate ($1.00), contract terms, and math are supported, but the key facts the dispute turns on—the ad-proof showing features only ran weeks ending 10/26 and 11/09, and the POS scan counts (1,030 and 1,015)—are asserted without being cited in the evidence, leaving an obvious opening to contest which weeks were featured and the eligible unit counts.
    - judge/no_unsupported: POS scan figures (1,030/1,015 feature-week, 1,120/1,050 non-feature), the ad-proof attachment confirming feature weeks, and the VM-90390 no-duplicate check are asserted but not present in the cited evidence.
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t2/D-0011/record.json
- **D-0013** [escalate] trial=t0
    - action_correct: drafted='deny' expected='escalate'
    - judge/no_unsupported: The justification asserts a search of the authorized promotion calendar 'returned no MDF authorization' and references a 'campaign-report attachment' and remittance text, none of which appear in the cited evidence.
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t0/D-0013/record.json
- **D-0013** [escalate] trial=t1
    - action_correct: drafted='deny' expected='escalate'
    - judge/no_unsupported: The justification claims 'The MDF contract section exhaustively defines' and 'use of are (not include) signals an exhaustive list' — the contract does not itself state exhaustiveness; this is an unsupported interpretive assertion. Also claims '5.3 requires pre-deduction approval' but §5.3 only says claims are 'subject to Meridian review,' and asserts 'No pre-authorization is on file' without any evidence of a checked file.
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t1/D-0013/record.json
- **D-0013** [escalate] trial=t2
    - action_correct: drafted='deny' expected='escalate'
    - judge/consistent: Justification cites a promo-calendar search and absence of settlement history for VM-90501 as evidence, but no such promo-calendar or settlement-history evidence is provided; the ineligible-activity and no-authorization grounds do follow from §5.2/§3.1, but the unsupported factual claims are not reconcilable with the cited evidence.
    - judge/no_unsupported: The justification claims a search of the ValuMax promo calendar returned no authorization and that no settlement history exists for VM-90501, but no such promo-calendar or settlement-history evidence is cited among the sources.
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t2/D-0013/record.json
- **D-0016** [ambiguous] trial=t0
    - action_correct: drafted='partial' expected='escalate'
    - judge/no_unsupported: The POS scan figures (10,540 units, 6 weekly periods) and store photo details (6 stores/locations) are not present in any cited evidence, making them unsupported invented claims.
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t0/D-0016/record.json
- **D-0016** [ambiguous] trial=t1
    - action_correct: drafted='partial' expected='escalate'
    - judge/consistent: Justification says $200/event is 'used as the operative rate,' yet 32 events × $200 = $6,400 and the settlement applies 60% to that claimed amount; but if the operative rate were truly applied, the corroborated 6 stores don't reconcile — more critically, the claim total $6,400 implies $200/event while promo authorizes $250, and the 60%×$6,400=$3,840 arithmetic is internally correct, but the rate reasoning contradicts itself by both citing $200 as operative and settling on claimed dollars.
    - judge/no_unsupported: The POS scan data claim (consistent week-over-week lift for both SKUs across six weeks, 10,540 total units) and the '6 stores' photo detail are cited as corroboration but no such POS/photo evidence appears in the provided source evidence.
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t1/D-0016/record.json
- **D-0016** [ambiguous] trial=t2
    - action_correct: drafted='partial' expected='escalate'
    - judge/no_unsupported: The scan data details (10,540 units, six reporting weeks, both SKUs) and the store-photo count of 6 stores are not established by any cited evidence; no POS scan data or photo exhibit appears in the source, making these corroboration claims unsupported.
    - transcript: /Users/ejochims/Documents/projects/deductions-agent-cma/runs/t2/D-0016/record.json

