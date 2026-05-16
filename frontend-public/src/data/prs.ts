import type { ContentPrSummary } from "../types";

export const CONTENT_PRS: readonly ContentPrSummary[] = [
  {
    id: "PR-142",
    disease: "fd",
    title: "Update: denosumab dosing schedule for pediatric polyostotic FD",
    opened: "2026-05-08",
    status: "under-review",
  },
  {
    id: "PR-141",
    disease: "fd",
    title: "Add: optic canal monitoring protocol for asymptomatic patients",
    opened: "2026-05-05",
    status: "pending",
  },
  {
    id: "PR-140",
    disease: "fd",
    title: "Clarify: when to refer for genetic testing vs histology alone",
    opened: "2026-04-28",
    status: "pending",
  },
  {
    id: "PR-139",
    disease: "mas",
    title: "Endocrine surveillance intervals in MAS",
    opened: "2026-05-01",
    status: "under-review",
  },
  {
    id: "PR-138",
    disease: "noonan",
    title: "Cardiology follow-up after pulmonary valve intervention",
    opened: "2026-05-11",
    status: "pending",
  },
  {
    id: "PR-137",
    disease: "noonan",
    title: "Growth hormone eligibility criteria — RASopathy panel",
    opened: "2026-05-09",
    status: "pending",
  },
  {
    id: "PR-136",
    disease: "noonan",
    title: "Bleeding risk with antiplatelet therapy",
    opened: "2026-05-07",
    status: "pending",
  },
  {
    id: "PR-135",
    disease: "noonan",
    title: "School accommodation guidance for cognitive support",
    opened: "2026-05-04",
    status: "pending",
  },
  {
    id: "PR-134",
    disease: "noonan",
    title: "Lymphatic malformation — imaging triggers",
    opened: "2026-05-02",
    status: "pending",
  },
] as const;
