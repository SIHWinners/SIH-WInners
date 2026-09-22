/**
 * Offline evaluation of the rules bundle (GET /v1/rules/bundle). Mirrors
 * services/core/app/modules/eligibility/service.py so phones get the same list, trace and
 * offer the server would give. Results are flagged provisional by the caller.
 */
import { evaluateScheme, normaliseFacts, type BundleCondition, type Json, type TraceRow } from './rules';

export interface BundleScheme {
  code: string;
  version: number;
  apex_corp: string;
  loan_type: string;
  name: Record<string, string>;
  source_url: string;
  verified_on: string | null;
  needs_verification: boolean;
  params: Record<string, Json>;
  conditions: BundleCondition[];
  documents_required: Array<{ type: string; required: boolean; validity_months?: number }>;
  loan_limits: { min_paise: number; max_paise: number };
  funding_pattern: { apex_bps: number; partner_bps: number; beneficiary_bps: number };
  interest: { slabs: Array<{ upto_paise: number; rate_bps: number }>; women_rebate_bps?: number };
  moratorium: { default_months: number; max_months: number; treatment: string };
  repayment: { default_tenure_months: number; max_tenure_months: number; frequency: string };
  channel_partner_types: string[];
  processing_days: number;
}

export interface RulesBundle {
  etag: string;
  schemes: BundleScheme[];
}

export function rateFor(scheme: BundleScheme, principal: number, gender?: string | null): number {
  const slabs = [...scheme.interest.slabs].sort((a, b) => a.upto_paise - b.upto_paise);
  let rate = (slabs.find((s) => principal <= s.upto_paise) ?? slabs[slabs.length - 1]!).rate_bps;
  if (gender === 'female') rate -= scheme.interest.women_rebate_bps ?? 0;
  return rate;
}

export function buildOffer(scheme: BundleScheme, facts: Record<string, Json>) {
  const maxLoan = scheme.loan_limits.max_paise;
  let wanted: number | null = facts.loan_needed_paise ?? null;
  if (wanted === null && typeof facts.project_cost_paise === 'number') {
    wanted = Math.floor((facts.project_cost_paise * scheme.funding_pattern.apex_bps) / 10000);
  }
  const principal = wanted === null ? null : Math.min(wanted, maxLoan);
  return {
    rate_bps: rateFor(scheme, principal ?? 0, facts.gender),
    max_loan_paise: maxLoan,
    suggested_principal_paise: principal,
    default_tenure_months: scheme.repayment.default_tenure_months,
    max_tenure_months: scheme.repayment.max_tenure_months,
    moratorium_default_months: scheme.moratorium.default_months,
    moratorium_max_months: scheme.moratorium.max_months,
    moratorium_treatment: scheme.moratorium.treatment,
    repayment_frequency: scheme.repayment.frequency,
    funding_pattern: scheme.funding_pattern,
    processing_days: scheme.processing_days,
  };
}

export interface OfflineResult {
  code: string;
  name: Record<string, string>;
  apex_corp: string;
  loan_type: string;
  version: number;
  rule_version_id: null;
  source_url: string;
  verified_on: string | null;
  needs_verification: boolean;
  status: 'eligible' | 'ineligible' | 'needs_info';
  trace: TraceRow[];
  failed: string[];
  missing: string[];
  near_miss: TraceRow | null;
  documents_required: BundleScheme['documents_required'];
  channel_partner_types: string[];
  offer: ReturnType<typeof buildOffer>;
}

export function evaluateBundle(bundle: RulesBundle, applicant: Record<string, Json>) {
  const facts = normaliseFacts(applicant);
  const results: OfflineResult[] = [...bundle.schemes]
    .sort((a, b) => (a.code < b.code ? -1 : 1))
    .map((s) => ({
      code: s.code, name: s.name, apex_corp: s.apex_corp, loan_type: s.loan_type, version: s.version,
      rule_version_id: null, source_url: s.source_url, verified_on: s.verified_on,
      needs_verification: s.needs_verification, documents_required: s.documents_required,
      channel_partner_types: s.channel_partner_types, offer: buildOffer(s, facts),
      ...evaluateScheme(s.conditions, facts, s.params),
    }));
  const eligible = results
    .filter((r) => r.status === 'eligible')
    .sort((a, b) => a.offer.rate_bps - b.offer.rate_bps
      || b.offer.funding_pattern.apex_bps - a.offer.funding_pattern.apex_bps
      || (a.code < b.code ? -1 : 1));
  return {
    rules_etag: bundle.etag,
    eligible: eligible.map((r) => r.code),
    ineligible: results.filter((r) => r.status === 'ineligible').map((r) => r.code),
    needs_info: results.filter((r) => r.status === 'needs_info').map((r) => r.code),
    near_misses: results.filter((r) => r.status === 'ineligible' && r.near_miss).map((r) => r.code),
    next_best: eligible[0]?.code ?? null,
    results,
  };
}
