"""
Department Routing Service with Hybrid Search.
Routes complaints/reviews to appropriate departments using BM25 + Embedding + Rerank.
"""

import logging
import re
import yaml
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from pydantic import ValidationError
from app.schemas.service_models import TeamInfo as PydanticTeamInfo
from app.agents.embedding_service import EmbeddingService, get_embedding_service
from app.agents.rerank_service import RerankService, get_rerank_service
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"


@dataclass
class TeamInfo:
    """Team information within a division."""
    code: str
    name: str
    description: str
    division_code: str
    division_name: str
    keywords: List[str] = field(default_factory=list)
    representative_sentences: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None

    @property
    def full_code(self) -> str:
        """Get full hierarchical code (DIVISION.TEAM)."""
        return f"{self.division_code}.{self.code}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'code': self.code,
            'full_code': self.full_code,
            'name': self.name,
            'description': self.description,
            'division_code': self.division_code,
            'division_name': self.division_name
        }


@dataclass
class RoutingCandidate:
    """Candidate department for routing."""
    team: TeamInfo
    bm25_score: float = 0.0
    embedding_score: float = 0.0
    rerank_score: float = 0.0
    combined_score: float = 0.0
    role: str = "primary"
    matched_keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'code': self.team.full_code,
            'name': self.team.name,
            'division_name': self.team.division_name,
            'role': self.role,
            'scores': {
                'bm25': round(self.bm25_score, 4),
                'embedding': round(self.embedding_score, 4),
                'rerank': round(self.rerank_score, 4),
                'combined': round(self.combined_score, 4)
            },
            'matched_keywords': self.matched_keywords
        }


@dataclass
class RoutingResult:
    """Result of department routing."""
    primary: RoutingCandidate
    secondary: List[RoutingCandidate] = field(default_factory=list)
    escalation_required: bool = False
    escalation_level: Optional[str] = None
    urgency: int = 1
    sla_hours: int = 168
    collaboration_rule_applied: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'primary_dept': {
                'code': self.primary.team.full_code,
                'name': self.primary.team.name,
                'division_name': self.primary.team.division_name
            },
            'secondary_depts': [
                {
                    'code': c.team.full_code,
                    'name': c.team.name,
                    'role': c.role
                }
                for c in self.secondary
            ],
            'escalation_required': self.escalation_required,
            'escalation_level': self.escalation_level,
            'urgency': self.urgency,
            'sla_hours': self.sla_hours,
            'routing_scores': {
                'primary': self.primary.to_dict()['scores'],
                'method': 'hybrid_bm25_embedding_rerank'
            }
        }


class DepartmentRoutingService:
    """
    Service for routing complaints/reviews to appropriate departments.

    Uses hybrid search combining:
    1. BM25 (keyword matching with TF-IDF)
    2. Embedding similarity (bge-m3-ko)
    3. Reranking (bge-reranker-v2-m3)

    Also handles:
    - Multi-department collaboration rules
    - Escalation based on urgency
    """

    # Weights for combining scores
    BM25_WEIGHT = 0.3
    EMBEDDING_WEIGHT = 0.4
    RERANK_WEIGHT = 0.3

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        rerank_service: Optional[RerankService] = None
    ):
        self._embedding_service = embedding_service
        self._rerank_service = rerank_service
        self._hierarchy: Dict[str, Any] = {}
        self._teams: Dict[str, TeamInfo] = {}
        self._collaboration_rules: List[Dict[str, Any]] = []
        self._escalation_rules: Dict[str, Dict[str, Any]] = {}
        self._keyword_index: Dict[str, List[str]] = {}  # keyword -> [team_codes]
        self._team_embeddings_initialized = False

        self._load_hierarchy()
        self._build_keyword_index()

    def _load_hierarchy(self):
        """Load department hierarchy from MariaDB (DB-based routing)."""
        from app.core.mysql_client import get_mysql_client
        import json
        
        logger.info("Loading department hierarchy from database...")
        
        try:
            mysql = get_mysql_client()
            
            # Optimized: Single JOIN query to load all data (Critical #8 fix)
            query = """
            SELECT 
                t.team_id, t.team_code, t.division_code,
                t.name as team_name, t.description as team_desc,
                t.embedding_vector,
                d.name as division_name,
                k.keyword,
                s.sentence, s.priority
            FROM routing_teams t
            JOIN routing_divisions d ON t.division_code = d.division_code
            LEFT JOIN routing_keywords k ON t.team_id = k.team_id
            LEFT JOIN routing_sentences s ON t.team_id = s.team_id
            ORDER BY t.team_id, s.priority, k.keyword_id
            """
            rows = mysql.execute_all(query)
            logger.info(f"Loaded {len(rows)} rows from database")
            
            # Group by team (Python-side grouping)
            teams_dict = {}
            for row in rows:
                team_key = f"{row['division_code']}.{row['team_code']}"
                
                if team_key not in teams_dict:
                    teams_dict[team_key] = {
                        'team_id': row['team_id'],
                        'team_code': row['team_code'],
                        'division_code': row['division_code'],
                        'team_name': row['team_name'],
                        'team_desc': row['team_desc'],
                        'division_name': row['division_name'],
                        'embedding_vector': row['embedding_vector'],
                        'keywords': [],
                        'sentences': []
                    }
                
                # Add keyword (avoid duplicates)
                if row['keyword'] and row['keyword'] not in teams_dict[team_key]['keywords']:
                    teams_dict[team_key]['keywords'].append(row['keyword'])
                
                # Add sentence (preserve order)
                if row['sentence'] and row['sentence'] not in teams_dict[team_key]['sentences']:
                    teams_dict[team_key]['sentences'].append(row['sentence'])
            
            # Create TeamInfo objects with Pydantic validation
            for full_code, data in teams_dict.items():
                # Parse embedding vector (Critical #2 fix)
                embedding = None
                if data['embedding_vector']:
                    try:
                        embedding = json.loads(data['embedding_vector'])
                        dims = get_settings().bge.embedding_dimensions
                        if not isinstance(embedding, list) or len(embedding) != dims:
                            logger.warning(f"Invalid embedding for {full_code}: expected {dims}-dim list")
                            embedding = None
                    except Exception as e:
                        logger.warning(f"Failed to parse embedding for {full_code}: {e}")

                # Validate with Pydantic
                try:
                    pydantic_data = {
                        'code': data['team_code'],
                        'name': data['team_name'],
                        'description': data['team_desc'],
                        'division_code': data['division_code'],
                        'division_name': data['division_name'],
                        'keywords': data['keywords'],
                        'representative_sentences': data['sentences']
                    }
                    pydantic_team = PydanticTeamInfo.model_validate(pydantic_data)

                    # Create dataclass TeamInfo with validated data + embedding
                    team_info = TeamInfo(
                        code=pydantic_team.code,
                        name=pydantic_team.name,
                        description=pydantic_team.description or '',
                        division_code=pydantic_team.division_code,
                        division_name=pydantic_team.division_name or '',
                        keywords=pydantic_team.keywords,
                        representative_sentences=pydantic_team.representative_sentences,
                        embedding=embedding
                    )
                    self._teams[full_code] = team_info

                except ValidationError as ve:
                    logger.error(
                        f"Team validation failed for {full_code}: "
                        f"{ve.error_count()} errors. Skipping team."
                    )
                    logger.error(f"Validation errors: {ve.errors()}")
                    continue
            
            # Load collaboration rules
            collab_rules = mysql.execute_all(
                "SELECT * FROM routing_collaboration_rules WHERE is_active = TRUE"
            )
            self._collaboration_rules = []
            for rule in collab_rules:
                self._collaboration_rules.append({
                    'trigger_keywords': json.loads(rule['trigger_keywords']),
                    'secondary': json.loads(rule['secondary_depts'])
                })
            
            # Load escalation rules
            esc_rules = mysql.execute_all(
                "SELECT * FROM routing_escalation_rules WHERE is_active = TRUE"
            )
            self._escalation_rules = {}
            for rule in esc_rules:
                self._escalation_rules[rule['rule_name']] = {
                    'keywords': json.loads(rule['keywords']),
                    'urgency': rule['urgency'],
                    'escalation_level': rule['escalation_level'],
                    'sla_hours': rule['sla_hours']
                }
            
            # Check if embeddings are loaded
            self._team_embeddings_initialized = any(
                team.embedding is not None for team in self._teams.values()
            )
            
            logger.info(f"✅ Loaded {len(self._teams)} teams from database")
            logger.info(f"   - {sum(1 for t in self._teams.values() if t.embedding)} teams with embeddings")
            logger.info(f"   - {len(self._collaboration_rules)} collaboration rules")
            logger.info(f"   - {len(self._escalation_rules)} escalation rules")
            
        except Exception as e:
            logger.warning(f"Failed to load hierarchy from DB: {e}")
            logger.info("Falling back to YAML configuration...")
            self._load_from_yaml()

    def _load_from_yaml(self):
        """Load department hierarchy from YAML config."""
        config_path = CONFIG_DIR / "department_hierarchy.yaml"
        
        if not config_path.exists():
            logger.error(f"Config file not found: {config_path}")
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # Load divisions and teams
            divisions = config.get('divisions', {})
            for div_code, div_data in divisions.items():
                div_name = div_data.get('name', div_code)
                teams = div_data.get('teams', {})
                
                for team_code, team_data in teams.items():
                    full_code = f"{div_code}.{team_code}"
                    
                    team_info = TeamInfo(
                        code=team_code,
                        name=team_data.get('name', team_code),
                        description=team_data.get('description', ''),
                        division_code=div_code,
                        division_name=div_name,
                        keywords=team_data.get('keywords', []),
                        representative_sentences=team_data.get('representative_sentences', []),
                        embedding=None  # Embeddings will be generated lazily
                    )
                    self._teams[full_code] = team_info

            # Load collaboration rules
            self._collaboration_rules = config.get('collaboration_rules', [])
            
            # Load escalation rules
            self._escalation_rules = config.get('escalation_rules', {})

            logger.info(f"✅ Loaded {len(self._teams)} teams from YAML")
            logger.info(f"   - {len(self._collaboration_rules)} collaboration rules")
            logger.info(f"   - {len(self._escalation_rules)} escalation rules")

        except Exception as e:
            logger.error(f"Failed to load hierarchy from YAML: {e}")
            raise

    def _build_keyword_index(self):
        """Build inverted index from keywords to teams."""
        self._keyword_index = {}

        for team_code, team in self._teams.items():
            for keyword in team.keywords:
                keyword_lower = keyword.lower()
                if keyword_lower not in self._keyword_index:
                    self._keyword_index[keyword_lower] = []
                self._keyword_index[keyword_lower].append(team_code)

        logger.info(f"Built keyword index with {len(self._keyword_index)} keywords")

    async def _ensure_embeddings_initialized(self):
        """Initialize team embeddings lazily."""
        if self._team_embeddings_initialized:
            return

        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()

        # Generate embeddings for each team using representative sentences
        for team_code, team in self._teams.items():
            if team.representative_sentences:
                # Combine representative sentences for embedding
                combined_text = " ".join(team.representative_sentences[:5])
                try:
                    result = await self._embedding_service.embed(combined_text)
                    team.embedding = result.embedding
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for {team_code}: {e}")
                    team.embedding = None

        self._team_embeddings_initialized = True
        logger.info("Team embeddings initialized")

    def _compute_bm25_scores(
        self,
        text: str,
        candidates: List[str]
    ) -> Dict[str, Tuple[float, List[str]]]:
        """
        Compute BM25-like scores for candidates based on keyword matching.

        Returns:
            Dict mapping team_code to (score, matched_keywords)
        """
        # Tokenize input text (simple Korean tokenization)
        text_lower = text.lower()
        tokens = set(re.findall(r'[가-힣a-z0-9]+', text_lower))

        scores: Dict[str, Tuple[float, List[str]]] = {}

        for team_code in candidates:
            team = self._teams.get(team_code)
            if not team:
                continue

            matched_keywords = []
            score = 0.0

            for keyword in team.keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in text_lower or keyword_lower in tokens:
                    matched_keywords.append(keyword)
                    # Weight by inverse document frequency (rarer keyword = higher score)
                    idf = 1.0 / len(self._keyword_index.get(keyword_lower, [team_code]))
                    score += idf

            # Normalize by number of keywords
            if team.keywords:
                score = score / np.sqrt(len(team.keywords))

            scores[team_code] = (score, matched_keywords)

        return scores

    async def _compute_embedding_scores(
        self,
        text: str,
        candidates: List[str]
    ) -> Dict[str, float]:
        """Compute embedding similarity scores for candidates."""
        await self._ensure_embeddings_initialized()

        if self._embedding_service is None:
            return {c: 0.0 for c in candidates}

        try:
            # Get embedding for input text
            result = await self._embedding_service.embed(text)
            query_embedding = np.array(result.embedding)

            scores = {}
            for team_code in candidates:
                team = self._teams.get(team_code)
                if not team or team.embedding is None:
                    scores[team_code] = 0.0
                    continue

                # Cosine similarity
                team_embedding = np.array(team.embedding)
                similarity = np.dot(query_embedding, team_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(team_embedding) + 1e-8
                )
                scores[team_code] = float(max(0, similarity))

            return scores

        except Exception as e:
            logger.warning(f"Embedding similarity failed: {e}")
            return {c: 0.0 for c in candidates}

    async def _compute_rerank_scores(
        self,
        text: str,
        candidates: List[str]
    ) -> Dict[str, float]:
        """Compute rerank scores using cross-encoder."""
        if self._rerank_service is None:
            self._rerank_service = get_rerank_service()

        try:
            # Build documents for reranking (team description + keywords)
            documents = []
            for team_code in candidates:
                team = self._teams.get(team_code)
                if team:
                    doc = f"{team.name}: {team.description}. 키워드: {', '.join(team.keywords[:10])}"
                    documents.append(doc)
                else:
                    documents.append("")

            # Get rerank scores
            rerank_results = await self._rerank_service.rerank(
                query=text,
                documents=documents,
                top_n=len(documents)
            )

            scores = {}
            for i, team_code in enumerate(candidates):
                # Find score for this candidate
                for result in rerank_results.results:
                    if result.index == i:
                        scores[team_code] = result.score
                        break
                else:
                    scores[team_code] = 0.0

            return scores

        except Exception as e:
            logger.warning(f"Rerank failed: {e}")
            return {c: 0.0 for c in candidates}

    def _get_initial_candidates(self, text: str) -> List[str]:
        """Get initial candidate teams based on keyword matching."""
        text_lower = text.lower()
        tokens = set(re.findall(r'[가-힣a-z0-9]+', text_lower))

        candidates = set()

        # Find teams with matching keywords
        for keyword, team_codes in self._keyword_index.items():
            if keyword in text_lower or keyword in tokens:
                candidates.update(team_codes)

        # If no matches, return all teams
        if not candidates:
            candidates = set(self._teams.keys())

        return list(candidates)

    def _check_collaboration_rules(
        self,
        text: str,
        primary_team_code: str
    ) -> List[Tuple[str, str]]:
        """
        Check if collaboration rules apply.

        Returns:
            List of (team_full_code, role) tuples for secondary departments
        """
        text_lower = text.lower()
        secondary = []

        for rule in self._collaboration_rules:
            trigger_keywords = rule.get('trigger_keywords', [])

            # Check if any trigger keyword matches
            triggered = any(kw.lower() in text_lower for kw in trigger_keywords)

            if triggered:
                # Add secondary departments from this rule
                for sec_dept in rule.get('secondary', []):
                    division = sec_dept.get('division', '')
                    team = sec_dept.get('team', '')
                    role = sec_dept.get('role', 'support')

                    full_code = f"{division}.{team}"

                    # Don't add if it's the primary team
                    if full_code != primary_team_code and full_code in self._teams:
                        secondary.append((full_code, role))

        # Remove duplicates while preserving order
        seen = set()
        unique_secondary = []
        for item in secondary:
            if item[0] not in seen:
                seen.add(item[0])
                unique_secondary.append(item)

        return unique_secondary

    def _check_escalation_rules(self, text: str) -> Tuple[bool, Optional[str], int, int]:
        """
        Check if escalation rules apply.

        Returns:
            Tuple of (escalation_required, escalation_level, urgency, sla_hours)
        """
        text_lower = text.lower()

        highest_urgency = 1
        escalation_required = False
        escalation_level = None
        sla_hours = 168  # Default 7 days

        for rule_name, rule in self._escalation_rules.items():
            keywords = rule.get('keywords', [])

            # Check if any keyword matches
            triggered = any(kw.lower() in text_lower for kw in keywords)

            if triggered:
                rule_urgency = rule.get('urgency', 1)
                if rule_urgency > highest_urgency:
                    highest_urgency = rule_urgency
                    escalation_required = True
                    escalation_level = rule.get('escalation_level', 'staff')
                    sla_hours = rule.get('sla_hours', 168)

        return escalation_required, escalation_level, highest_urgency, sla_hours

    async def route(
        self,
        text: str,
        top_k: int = 5,
        include_secondary: bool = True
    ) -> RoutingResult:
        """
        Route a complaint/review to appropriate department(s).

        Args:
            text: The complaint/review text
            top_k: Number of top candidates to consider for reranking
            include_secondary: Whether to include secondary departments

        Returns:
            RoutingResult with primary and secondary departments
        """
        # Step 1: Get initial candidates via keyword matching
        candidates = self._get_initial_candidates(text)
        logger.debug(f"Initial candidates: {len(candidates)}")

        # Step 2: Compute BM25 scores
        bm25_results = self._compute_bm25_scores(text, candidates)

        # Step 3: Compute embedding scores
        embedding_scores = await self._compute_embedding_scores(text, candidates)

        # Step 4: Combine BM25 and embedding scores to get top-k for reranking
        combined_pre_rerank = {}
        for team_code in candidates:
            bm25_score, _ = bm25_results.get(team_code, (0.0, []))
            emb_score = embedding_scores.get(team_code, 0.0)
            combined_pre_rerank[team_code] = (
                self.BM25_WEIGHT * bm25_score +
                (self.EMBEDDING_WEIGHT + self.RERANK_WEIGHT) * emb_score
            )

        # Sort and get top-k
        top_candidates = sorted(
            combined_pre_rerank.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        top_candidate_codes = [c[0] for c in top_candidates]

        # Step 5: Rerank top candidates
        rerank_scores = await self._compute_rerank_scores(text, top_candidate_codes)

        # Step 6: Compute final combined scores
        routing_candidates = []
        for team_code in top_candidate_codes:
            bm25_score, matched_keywords = bm25_results.get(team_code, (0.0, []))
            emb_score = embedding_scores.get(team_code, 0.0)
            rerank_score = rerank_scores.get(team_code, 0.0)

            combined = (
                self.BM25_WEIGHT * bm25_score +
                self.EMBEDDING_WEIGHT * emb_score +
                self.RERANK_WEIGHT * rerank_score
            )

            candidate = RoutingCandidate(
                team=self._teams[team_code],
                bm25_score=bm25_score,
                embedding_score=emb_score,
                rerank_score=rerank_score,
                combined_score=combined,
                matched_keywords=matched_keywords
            )
            routing_candidates.append(candidate)

        # Sort by combined score
        routing_candidates.sort(key=lambda x: x.combined_score, reverse=True)

        if not routing_candidates:
            # Critical #5: DB-based fallback with ultimate hardcoded safety
            logger.warning("No routing candidates found, using fallback")
            
            # Try to get fallback from DB
            fallback_team = self._teams.get("CUSTOMER_SERVICE.CALL_CENTER")
            
            if fallback_team:
                # DB fallback succeeded
                logger.info("Using DB fallback: CUSTOMER_SERVICE.CALL_CENTER")
                primary = RoutingCandidate(team=fallback_team)
            else:
                # Ultimate fallback: DB 실패 시에도 서비스 유지
                logger.error("DB fallback failed, using ultimate configured fallback")
                settings = get_settings()
                fb_config = settings.fallback_department

                primary = RoutingCandidate(
                    team=TeamInfo(
                        code=fb_config.code.split('.')[-1],  # "CALL_CENTER"
                        name=fb_config.name,
                        description=fb_config.description,
                        division_code=fb_config.division_code,
                        division_name=fb_config.division_name,
                        keywords=[],
                        representative_sentences=[]
                    )
                )
        else:
            primary = routing_candidates[0]

        # Step 7: Check collaboration rules for secondary departments
        secondary = []
        if include_secondary:
            collaboration_teams = self._check_collaboration_rules(text, primary.team.full_code)

            for team_code, role in collaboration_teams:
                team = self._teams.get(team_code)
                if team:
                    secondary.append(RoutingCandidate(
                        team=team,
                        role=role
                    ))

        # Step 8: Check escalation rules
        escalation_required, escalation_level, urgency, sla_hours = self._check_escalation_rules(text)

        return RoutingResult(
            primary=primary,
            secondary=secondary,
            escalation_required=escalation_required,
            escalation_level=escalation_level,
            urgency=urgency,
            sla_hours=sla_hours
        )

    def get_team_info(self, team_code: str) -> Optional[TeamInfo]:
        """Get team information by code."""
        return self._teams.get(team_code)

    def get_all_teams(self) -> Dict[str, TeamInfo]:
        """Get all teams."""
        return self._teams.copy()

    def get_division_teams(self, division_code: str) -> List[TeamInfo]:
        """Get all teams in a division."""
        return [
            team for team in self._teams.values()
            if team.division_code == division_code
        ]

    def format_for_prompt(self) -> str:
        """Format department hierarchy for LLM prompt."""
        lines = []

        # Group teams by division
        divisions: Dict[str, List[TeamInfo]] = {}
        for team in self._teams.values():
            if team.division_code not in divisions:
                divisions[team.division_code] = []
            divisions[team.division_code].append(team)

        for div_code, teams in divisions.items():
            div_name = teams[0].division_name if teams else div_code
            lines.append(f"\n[{div_code}] {div_name}")

            for team in teams:
                keywords_str = ", ".join(team.keywords[:7])
                lines.append(f"  - {team.full_code} ({team.name})")
                lines.append(f"    설명: {team.description}")
                lines.append(f"    키워드: {keywords_str}")

        return "\n".join(lines)


# Singleton instance
_routing_service: Optional[DepartmentRoutingService] = None


def get_department_routing_service() -> DepartmentRoutingService:
    """Get singleton DepartmentRoutingService instance."""
    global _routing_service
    if _routing_service is None:
        _routing_service = DepartmentRoutingService()
    return _routing_service
