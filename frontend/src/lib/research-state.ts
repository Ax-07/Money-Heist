export type ResearchReportType =
  | "SCANNER_FILTERING"
  | "FUNNEL_DECISION_QUALITY";

export type ResearchCohortSelector = {
  reportType: ResearchReportType;
  dimension: string;
  key: string;
  stage: string | null;
};

export type ResearchContrastSelection = {
  reportType: ResearchReportType;
  kind: string;
  left: ResearchCohortSelector;
  right: ResearchCohortSelector;
};
