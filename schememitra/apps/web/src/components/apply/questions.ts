import type { ApplicantFacts } from '@sm/contracts/client';

import type { Personal } from '@/stores/draft';

export type QuestionKind = 'text' | 'number' | 'money' | 'choice' | 'yesno' | 'tel' | 'pincode' | 'district';

export interface Question {
  id: string;
  kind: QuestionKind;
  labelKey: string;
  hintKey?: string;
  target: { scope: 'personal'; key: keyof Personal } | { scope: 'fact'; key: keyof ApplicantFacts };
  options?: readonly string[];
  optionPrefix?: string;
  min?: number;
  max?: number;
  optional?: boolean;
  when?: (facts: Partial<ApplicantFacts>) => boolean;
}

/** The whole intake, one question per screen. Voice intake (Phase 4) fills the same fields. */
export const QUESTIONS: Question[] = [
  { id: 'name', kind: 'text', labelKey: 'intake.name', hintKey: 'intake.name_hint', target: { scope: 'personal', key: 'full_name' } },
  { id: 'age', kind: 'number', labelKey: 'intake.age', min: 14, max: 90, target: { scope: 'fact', key: 'age' } },
  { id: 'gender', kind: 'choice', labelKey: 'intake.gender', options: ['female', 'male', 'other'], optionPrefix: 'options.gender', target: { scope: 'fact', key: 'gender' } },
  {
    id: 'social_category', kind: 'choice', labelKey: 'intake.social_category', hintKey: 'intake.social_category_hint',
    options: ['sc', 'st', 'obc', 'safai_karamchari', 'minority', 'general'], optionPrefix: 'options.social_category',
    target: { scope: 'fact', key: 'social_category' },
  },
  { id: 'has_disability', kind: 'yesno', labelKey: 'intake.disability', target: { scope: 'fact', key: 'has_disability' } },
  {
    id: 'disability_pct', kind: 'number', labelKey: 'intake.disability_pct', min: 1, max: 100,
    target: { scope: 'fact', key: 'disability_pct' }, when: (f) => f.has_disability === true,
  },
  { id: 'state', kind: 'choice', labelKey: 'intake.state', options: ['GJ', 'RJ', 'UP', 'MH', 'TN'], optionPrefix: 'options.states', target: { scope: 'fact', key: 'state_code' } },
  { id: 'district', kind: 'district', labelKey: 'intake.district', target: { scope: 'fact', key: 'district_code' } },
  { id: 'pincode', kind: 'pincode', labelKey: 'intake.pincode', target: { scope: 'fact', key: 'pincode' }, optional: true },
  { id: 'income', kind: 'money', labelKey: 'intake.annual_income', hintKey: 'intake.annual_income_hint', target: { scope: 'fact', key: 'annual_family_income_paise' } },
  {
    id: 'education', kind: 'choice', labelKey: 'intake.education',
    options: ['none', 'primary', 'secondary', 'higher_secondary', 'diploma', 'graduate', 'postgraduate'], optionPrefix: 'options.education',
    target: { scope: 'fact', key: 'education_level' },
  },
  {
    id: 'business_type', kind: 'choice', labelKey: 'intake.business_type',
    options: ['dairy', 'tailoring', 'e_rickshaw', 'retail_shop', 'handicraft', 'agriculture', 'services', 'sanitation_enterprise', 'education'],
    optionPrefix: 'options.business_type', target: { scope: 'fact', key: 'business_type' },
  },
  {
    id: 'course_admitted', kind: 'yesno', labelKey: 'intake.course_admitted', target: { scope: 'fact', key: 'course_admitted' },
    when: (f) => f.business_type === 'education',
  },
  { id: 'project_cost', kind: 'money', labelKey: 'intake.project_cost', hintKey: 'intake.project_cost_hint', target: { scope: 'fact', key: 'project_cost_paise' } },
  { id: 'loan_needed', kind: 'money', labelKey: 'intake.loan_needed', target: { scope: 'fact', key: 'loan_needed_paise' } },
  { id: 'shg_member', kind: 'yesno', labelKey: 'intake.shg_member', target: { scope: 'fact', key: 'shg_member' } },
  { id: 'existing_loans', kind: 'yesno', labelKey: 'intake.existing_loans', target: { scope: 'fact', key: 'existing_loans' } },
  { id: 'phone', kind: 'tel', labelKey: 'intake.phone', target: { scope: 'personal', key: 'phone' }, optional: true },
];

export function visibleQuestions(facts: Partial<ApplicantFacts>): Question[] {
  return QUESTIONS.filter((q) => !q.when || q.when(facts));
}

export function answerOf(q: Question, facts: Partial<ApplicantFacts>, personal: Personal): unknown {
  return q.target.scope === 'personal' ? personal[q.target.key] : facts[q.target.key];
}

export function isAnswered(q: Question, facts: Partial<ApplicantFacts>, personal: Personal): boolean {
  const v = answerOf(q, facts, personal);
  return v !== undefined && v !== null && v !== '';
}
