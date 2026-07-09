from __future__ import annotations

from .approval_executor import ApprovalExecutor
from .agentic_prompt_executor import AgenticPromptExecutor
from .code_executor import CodeExecutor
from .decision_executor import DecisionExecutor
from .evaluation_check_executor import EvaluationCheckExecutor
from .guideline_bibliography_write_executor import GuidelineBibliographyWriteExecutor
from .guideline_factcheck_load_executor import GuidelineFactcheckLoadExecutor
from .guideline_quote_extract_load_executor import GuidelineQuoteExtractLoadExecutor
from .guideline_monitor_search_executor import GuidelineMonitorSearchExecutor
from .guideline_shelf_load_executor import GuidelineShelfLoadExecutor
from .guideline_shelf_search_executor import GuidelineShelfSearchExecutor
from .guideline_shelf_write_executor import GuidelineShelfWriteExecutor
from .guideline_suggestion_writer_executor import GuidelineSuggestionWriterExecutor
from .guideline_synthesis_writer_executor import GuidelineSynthesisWriterExecutor
from .guidelines_rag_executor import GuidelinesRagExecutor
from .http_executor import HttpExecutor
from .merge_executor import MergeExecutor
from .pmid_verifier_executor import PmidVerifierExecutor
from .pmid_scrubber_executor import PmidScrubberExecutor
from .prompt_executor import PromptExecutor
from .pubmed_authors_fetch_executor import PubmedAuthorsFetchExecutor
from .doctor_finder_step_executor import DoctorFinderStepExecutor
from .doctor_finder_ai_justification_executor import DoctorFinderAiJustificationExecutor
from .parent_pathway_end_executor import ParentPathwayEndExecutor
from .parent_pathway_evidence_executor import ParentPathwayEvidenceExecutor
from .parent_pathway_load_executor import ParentPathwayLoadExecutor

EXECUTOR_REGISTRY = {
    "decision": DecisionExecutor,
    "prompt": PromptExecutor,
    "agentic_prompt": AgenticPromptExecutor,
    "code": CodeExecutor,
    "http": HttpExecutor,
    "guidelines_rag": GuidelinesRagExecutor,
    "pmid_verify": PmidVerifierExecutor,
    "pmid_scrub": PmidScrubberExecutor,
    "evaluation_check": EvaluationCheckExecutor,
    "guideline_bibliography_write": GuidelineBibliographyWriteExecutor,
    "guideline_factcheck_load": GuidelineFactcheckLoadExecutor,
    "guideline_quote_extract_load": GuidelineQuoteExtractLoadExecutor,
    "guideline_monitor_search": GuidelineMonitorSearchExecutor,
    "guideline_shelf_load": GuidelineShelfLoadExecutor,
    "guideline_shelf_search": GuidelineShelfSearchExecutor,
    "guideline_shelf_write": GuidelineShelfWriteExecutor,
    "guideline_suggestion_writer": GuidelineSuggestionWriterExecutor,
    "guideline_synthesis_writer": GuidelineSynthesisWriterExecutor,
    "merge": MergeExecutor,
    "approval": ApprovalExecutor,
    "pubmed_authors_fetch": PubmedAuthorsFetchExecutor,
    "doctor_finder_step": DoctorFinderStepExecutor,
    "doctor_finder_ai_justification": DoctorFinderAiJustificationExecutor,
    "parent_pathway_load": ParentPathwayLoadExecutor,
    "parent_pathway_evidence": ParentPathwayEvidenceExecutor,
    "parent_pathway_end": ParentPathwayEndExecutor,
}
