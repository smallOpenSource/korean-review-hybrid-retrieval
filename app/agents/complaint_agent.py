"""
Complaint Classification Agent.
Classifies complaints and assigns responsible departments.

Uses hybrid search (BM25 + Embedding + Rerank) for department routing.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from app.agents.base_agent import BaseAgent
from app.config.prompts import get_prompt_templates
from app.services.department_routing_service import (
    DepartmentRoutingService,
    get_department_routing_service,
    RoutingResult
)
from app.schemas.llm import (
    ComplaintResult, DepartmentInfo, ComplaintType,
    UrgencyLevel, EscalationLevel
)

logger = logging.getLogger(__name__)


class ComplaintAgent(BaseAgent):
    """
    Agent for classifying complaints and assigning departments.

    Uses hybrid search (BM25 + Embedding + Rerank) for department routing.

    Determines:
    - Whether review is a complaint
    - Complaint type and subtype
    - Urgency and severity levels
    - Primary responsible department (via hybrid search)
    - Secondary/supporting departments (via collaboration rules)
    - Escalation requirements
    """

    AGENT_TYPE = "complaint"
    TASK_TYPE = "complaint_classification"
    PROMPT_TEMPLATE_ID = "complaint_classification"
    CONFIDENCE_THRESHOLD = 0.75  # Higher threshold for complaint handling

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._routing_service: Optional[DepartmentRoutingService] = None
        self._department_codes = self._load_department_codes()

    def _get_routing_service(self) -> DepartmentRoutingService:
        """Get or initialize the department routing service."""
        if self._routing_service is None:
            self._routing_service = get_department_routing_service()
        return self._routing_service

    def _load_department_codes(self) -> Dict[str, Dict[str, Any]]:
        """Load department codes from routing service."""
        try:
            routing_service = self._get_routing_service()
            teams = routing_service.get_all_teams()

            # Convert to legacy format for backward compatibility
            codes = {}
            for full_code, team in teams.items():
                codes[full_code] = {
                    'name': team.name,
                    'description': team.description,
                    'keywords': team.keywords,
                    'division_name': team.division_name
                }
            return codes
        except Exception as e:
            logger.warning(f"Failed to load from routing service, using prompts config: {e}")
            prompts = get_prompt_templates()
            return prompts.get_department_codes()

    def _format_department_codes(self) -> str:
        """Format department codes for prompt using routing service."""
        try:
            routing_service = self._get_routing_service()
            return routing_service.format_for_prompt()
        except Exception as e:
            logger.warning(f"Failed to format from routing service: {e}")
            # Fallback to legacy format
            lines = []
            for code, info in self._department_codes.items():
                name = info.get('name', code)
                desc = info.get('description', '')
                keywords = ', '.join(info.get('keywords', [])[:5])
                lines.append(f"- {code} ({name}): {desc}")
                if keywords:
                    lines.append(f"  키워드: {keywords}")
            return "\n".join(lines)

    async def route_to_department(self, content: str) -> RoutingResult:
        """
        Route content to appropriate department using hybrid search.

        Args:
            content: The complaint/review content

        Returns:
            RoutingResult with primary and secondary departments
        """
        routing_service = self._get_routing_service()
        return await routing_service.route(content)

    def _prepare_prompt_variables(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare variables for complaint classification prompt."""
        return {
            'app_name': input_data.get('app_name', 'Unknown App'),
            'rating': input_data.get('rating', 'N/A'),
            'content': input_data.get('content', ''),
            'sentiment_label': input_data.get('sentiment_label', 'neutral'),
            'department_codes': self._format_department_codes(),
            'previous_complaints': input_data.get('previous_complaints', '')
        }

    def _parse_result(self, parsed_json: Dict[str, Any]) -> ComplaintResult:
        """Parse complaint result from LLM response."""
        result_data = parsed_json if isinstance(parsed_json, dict) else {}

        # Parse is_complaint
        is_complaint = bool(result_data.get('is_complaint', False))

        # Parse complaint type with defensive mapping
        type_str = result_data.get('complaint_type', 'general_review')

        # Defensive mapping for common LLM mistakes
        type_mappings = {
            'performance': 'dissatisfaction',
            '성능': 'dissatisfaction',
            'speed': 'dissatisfaction',
            'stability': 'error_report',
            '안정성': 'error_report',
        }

        if type_str in type_mappings:
            original_type = type_str
            type_str = type_mappings[type_str]
            logger.debug(f"Mapped complaint type: {original_type} → {type_str}")

        try:
            complaint_type = ComplaintType(type_str)
        except ValueError:
            complaint_type = ComplaintType.GENERAL_REVIEW

        # Parse sub_type
        sub_type = result_data.get('sub_type')

        # Parse urgency
        urgency_val = int(result_data.get('urgency', 1))
        urgency_val = max(1, min(4, urgency_val))
        urgency = UrgencyLevel(urgency_val)

        # Parse severity
        severity = int(result_data.get('severity', 1))
        severity = max(1, min(5, severity))

        # Parse primary department
        primary_data = result_data.get('primary_dept', {})
        primary_dept = self._parse_department(primary_data, role="primary")

        # Parse secondary departments
        secondary_data = result_data.get('secondary_depts', [])
        secondary_depts = [
            self._parse_department(d, role=d.get('role', 'support'))
            for d in secondary_data
        ]

        # Parse escalation
        escalation_required = bool(result_data.get('escalation_required', False))
        escalation_level = None
        if escalation_required:
            level_str = result_data.get('escalation_level', 'staff')
            level_mapping = {
                '담당자': EscalationLevel.STAFF,
                'staff': EscalationLevel.STAFF,
                '팀장': EscalationLevel.TEAM_LEAD,
                'team_lead': EscalationLevel.TEAM_LEAD,
                '본부장': EscalationLevel.DEPT_HEAD,
                'dept_head': EscalationLevel.DEPT_HEAD,
                '임원': EscalationLevel.EXECUTIVE,
                'executive': EscalationLevel.EXECUTIVE
            }
            escalation_level = level_mapping.get(level_str, EscalationLevel.STAFF)

        confidence = float(result_data.get('confidence', 0.5))

        return ComplaintResult(
            is_complaint=is_complaint,
            complaint_type=complaint_type,
            sub_type=sub_type,
            urgency=urgency,
            severity=severity,
            primary_dept=primary_dept,
            secondary_depts=secondary_depts,
            escalation_required=escalation_required,
            escalation_level=escalation_level,
            confidence=confidence
        )

    def _parse_department(
        self,
        data: Dict[str, Any],
        role: str = "primary"
    ) -> DepartmentInfo:
        """Parse department info from response."""
        code = data.get('code') or 'CUSTOMER_SERVICE.CALL_CENTER'

        # Validate department code
        if code not in self._department_codes:
            # Try to find a matching code (partial match)
            matched = False
            for full_code in self._department_codes.keys():
                if code in full_code or full_code.endswith(code):
                    code = full_code
                    matched = True
                    break

            if not matched:
                logger.warning(f"Unknown department code: {code}, defaulting to CUSTOMER_SERVICE.CALL_CENTER")
                code = 'CUSTOMER_SERVICE.CALL_CENTER'

        dept_info = self._department_codes.get(code, {})
        name = data.get('name') or dept_info.get('name') or code
        division_name = dept_info.get('division_name')

        return DepartmentInfo(
            code=code,
            name=name,
            role=role,
            division_name=division_name
        )

    def _convert_routing_result_to_department_info(
        self,
        routing_result: RoutingResult
    ) -> tuple:
        """Convert routing result to DepartmentInfo objects."""
        # Primary department
        primary = routing_result.primary
        primary_dept = DepartmentInfo(
            code=primary.team.full_code,
            name=primary.team.name,
            role="primary",
            division_name=primary.team.division_name,
            routing_scores={
                'bm25': primary.bm25_score,
                'embedding': primary.embedding_score,
                'rerank': primary.rerank_score,
                'combined': primary.combined_score
            }
        )

        # Secondary departments
        secondary_depts = []
        for sec in routing_result.secondary:
            secondary_depts.append(DepartmentInfo(
                code=sec.team.full_code,
                name=sec.team.name,
                role=sec.role,
                division_name=sec.team.division_name
            ))

        return primary_dept, secondary_depts

    def _extract_confidence(self, parsed_json: Dict[str, Any]) -> float:
        """Extract confidence from parsed response."""
        result = parsed_json.get('result', {})
        return float(result.get('confidence', 0.5))

    def _should_flag_for_review(
        self,
        confidence: float,
        result: ComplaintResult,
        reasoning
    ) -> bool:
        """Determine if complaint result needs human review."""
        # Always flag critical urgency complaints
        if result.urgency == UrgencyLevel.CRITICAL:
            return True

        # Always flag legal issues
        if result.complaint_type == ComplaintType.LEGAL_ISSUE:
            return True

        # Flag damage reports
        if result.complaint_type == ComplaintType.DAMAGE_REPORT:
            return True

        # Flag if escalation required
        if result.escalation_required:
            return True

        # Low confidence on complaint classification
        if confidence < self.CONFIDENCE_THRESHOLD:
            return True

        # High severity but low urgency (potential mismatch)
        if result.severity >= 4 and result.urgency.value <= 2:
            return True

        return super()._should_flag_for_review(confidence, result, reasoning)

    def get_sla_deadline_hours(self, result: ComplaintResult) -> int:
        """
        Get SLA deadline in hours based on urgency.

        Returns:
            Hours until deadline
        """
        sla_mapping = {
            UrgencyLevel.CRITICAL: 4,
            UrgencyLevel.HIGH: 24,
            UrgencyLevel.MEDIUM: 48,
            UrgencyLevel.LOW: 168  # 7 days
        }
        return sla_mapping.get(result.urgency, 168)

    async def analyze_with_routing(self, input_data: Dict[str, Any]) -> ComplaintResult:
        """
        Analyze complaint with hybrid department routing.

        This method combines:
        1. LLM-based complaint classification (type, severity, urgency)
        2. Hybrid search-based department routing (BM25 + Embedding + Rerank)

        Args:
            input_data: Input containing content, app_name, rating, etc.

        Returns:
            ComplaintResult with routing information
        """
        content = input_data.get('content', '')

        # Step 1: Get department routing via hybrid search
        routing_result = await self.route_to_department(content)

        # Step 2: Run LLM classification (this calls the parent analyze method)
        # The LLM will classify complaint type, severity, etc.
        # Department routing is already handled by hybrid search
        llm_result = await self.analyze(input_data)

        # Step 3: Merge routing results with LLM classification
        # Use hybrid routing for department assignment (more accurate)
        primary_dept, secondary_depts = self._convert_routing_result_to_department_info(routing_result)

        # Use escalation/urgency from routing if higher than LLM
        urgency = max(llm_result.urgency.value, routing_result.urgency)
        try:
            urgency_level = UrgencyLevel(urgency)
        except ValueError:
            urgency_level = llm_result.urgency

        escalation_required = llm_result.escalation_required or routing_result.escalation_required
        escalation_level = llm_result.escalation_level
        if routing_result.escalation_level and not escalation_level:
            level_mapping = {
                'staff': EscalationLevel.STAFF,
                'team_lead': EscalationLevel.TEAM_LEAD,
                'dept_head': EscalationLevel.DEPT_HEAD,
                'executive': EscalationLevel.EXECUTIVE
            }
            escalation_level = level_mapping.get(routing_result.escalation_level, EscalationLevel.STAFF)

        # Combine secondary departments from both sources
        existing_codes = {d.code for d in secondary_depts}
        for llm_sec in llm_result.secondary_depts:
            if llm_sec.code not in existing_codes:
                secondary_depts.append(llm_sec)

        return ComplaintResult(
            is_complaint=llm_result.is_complaint,
            complaint_type=llm_result.complaint_type,
            sub_type=llm_result.sub_type,
            urgency=urgency_level,
            severity=llm_result.severity,
            primary_dept=primary_dept,
            secondary_depts=secondary_depts,
            escalation_required=escalation_required,
            escalation_level=escalation_level,
            confidence=llm_result.confidence,
            sla_hours=routing_result.sla_hours,
            routing_method="hybrid_bm25_embedding_rerank"
        )


# Singleton instance
_complaint_agent: Optional[ComplaintAgent] = None


def get_complaint_agent() -> ComplaintAgent:
    """Get singleton ComplaintAgent instance."""
    global _complaint_agent
    if _complaint_agent is None:
        _complaint_agent = ComplaintAgent()
    return _complaint_agent
