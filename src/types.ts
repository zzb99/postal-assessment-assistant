export type PricingOption = { id: string; unit: string; unitPrice: number | null; condition: string; needsSupervisorReview?: boolean };

export type AssessmentRule = {
  id: string;
  stage: string;
  clause: string;
  name: string;
  original: string;
  pricingOptions: PricingOption[];
  applicableConditions: string;
  followUpResponsibility: string;
  version: string;
  needsSupervisorReview: boolean;
  keywords: string[];
};

export type AssessmentForm = {
  noticeNo: string;
  date: string;
  fillDate: string;
  shift: string;
  team?: string;
  company: string;
  inspector: string;
  stage: string;
  ruleId: string;
  pricingId: string;
  quantity: string;
  penaltyAmount: string;
  fact: string;
};

export type DocumentData = AssessmentForm & {
  rule: AssessmentRule;
  pricing: PricingOption;
  quantityNumber: number;
  amount: number;
  amountChinese: string;
  formattedDate: string;
  noticeSummary: string;
  itemText: string;
};

export type FieldErrors = Partial<Record<keyof AssessmentForm, string>>;
export type ExportState = 'idle' | 'loading' | 'success' | 'error';
