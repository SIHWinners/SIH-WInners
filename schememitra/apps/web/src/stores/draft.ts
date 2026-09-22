'use client';

import type { ApplicantFacts, EvaluateResponse, PartnerCard } from '@sm/contracts/client';
import type { Frequency, Treatment } from '@sm/contracts/finance';
import { create } from 'zustand';
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware';

export interface LoanPlan {
  principal_paise: number;
  rate_bps: number;
  tenure_months: number;
  moratorium_months: number;
  treatment: Treatment;
  frequency: Frequency;
}

export interface DocState {
  documentId?: string;
  status: 'missing' | 'uploading' | 'checking' | 'ok' | 'retake' | 'low_confidence' | 'failed';
  source?: 'camera' | 'upload' | 'digilocker';
  confidence?: number;
  issues?: string[];
  fields?: Record<string, unknown>;
}

export interface Personal {
  full_name?: string;
  father_name?: string;
  dob?: string;
  phone?: string;
}

export interface DraftState {
  clientUuid: string;
  startedAt: number;
  mode: 'form' | 'voice';
  personal: Personal;
  facts: Partial<ApplicantFacts>;
  intakeIndex: number;
  evaluation: (EvaluateResponse & { provisional: boolean; at: number }) | null;
  schemeCode: string | null;
  plan: LoanPlan | null;
  partner: PartnerCard | null;
  documents: Record<string, DocState>;
  applicationId: string | null;
  trackingId: string | null;
  hydrated: boolean;
  setFact: <K extends keyof ApplicantFacts>(key: K, value: ApplicantFacts[K] | undefined) => void;
  setFacts: (facts: Partial<ApplicantFacts>) => void;
  setPersonal: (patch: Personal) => void;
  setIntakeIndex: (i: number) => void;
  setMode: (mode: 'form' | 'voice') => void;
  setEvaluation: (e: DraftState['evaluation']) => void;
  chooseScheme: (code: string | null) => void;
  setPlan: (plan: LoanPlan | null) => void;
  choosePartner: (partner: PartnerCard | null) => void;
  setDocument: (type: string, patch: DocState) => void;
  setApplication: (id: string, trackingId: string | null) => void;
  reset: () => void;
}

const uuid = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

const blank = () => ({
  clientUuid: uuid(),
  startedAt: Date.now(),
  mode: 'form' as const,
  personal: {},
  facts: {},
  intakeIndex: 0,
  evaluation: null,
  schemeCode: null,
  plan: null,
  partner: null,
  documents: {},
  applicationId: null,
  trackingId: null,
});

// Drafts live in IndexedDB (survive reloads, offline, and big payloads); Dexie is loaded on
// first use so it never weighs on the landing page. Falls back to localStorage if IDB is blocked.
const idbStorage: StateStorage = {
  async getItem(name) {
    try {
      const { db } = await import('@/lib/local-db');
      return (await db.kv.get(name))?.value ?? null;
    } catch {
      return localStorage.getItem(name);
    }
  },
  async setItem(name, value) {
    try {
      const { db } = await import('@/lib/local-db');
      await db.kv.put({ key: name, value, updatedAt: Date.now() });
    } catch {
      localStorage.setItem(name, value);
    }
  },
  async removeItem(name) {
    try {
      const { db } = await import('@/lib/local-db');
      await db.kv.delete(name);
    } catch {
      localStorage.removeItem(name);
    }
  },
};

export const useDraft = create<DraftState>()(
  persist(
    (set) => ({
      ...blank(),
      hydrated: false,
      setFact: (key, value) =>
        set((s) => ({ facts: { ...s.facts, [key]: value }, evaluation: s.evaluation ? { ...s.evaluation, provisional: true } : null })),
      setFacts: (facts) => set((s) => ({ facts: { ...s.facts, ...facts } })),
      setPersonal: (patch) => set((s) => ({ personal: { ...s.personal, ...patch } })),
      setIntakeIndex: (intakeIndex) => set({ intakeIndex }),
      setMode: (mode) => set({ mode }),
      setEvaluation: (evaluation) => set({ evaluation }),
      chooseScheme: (schemeCode) => set({ schemeCode, plan: null, partner: null }),
      setPlan: (plan) => set({ plan }),
      choosePartner: (partner) => set({ partner }),
      setDocument: (type, patch) => set((s) => ({ documents: { ...s.documents, [type]: { ...s.documents[type], ...patch } } })),
      setApplication: (applicationId, trackingId) => set({ applicationId, trackingId }),
      reset: () => set({ ...blank() }),
    }),
    {
      name: 'sm-draft',
      version: 1,
      storage: createJSONStorage(() => idbStorage),
      partialize: ({ hydrated: _h, ...rest }) => rest,
      onRehydrateStorage: () => (state) => {
        if (state) state.hydrated = true;
        useDraft.setState({ hydrated: true });
      },
    },
  ),
);
