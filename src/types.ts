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
