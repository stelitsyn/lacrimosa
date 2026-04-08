"""Schema search functionality with keyword, semantic, and hybrid modes.

Search modes:
- keyword: Original lexical substring matching (exact/all/partial words)
- semantic: Embedding-based similarity using sentence-transformers
- hybrid: Combined scoring (70% semantic + 30% keyword)
"""

from pathlib import Path
from typing import Any, Optional

# Weight constants for hybrid search
SEMANTIC_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3


def search_schemas(
    query: str,
    schemas_dir: str,
    domain: Optional[str] = None,
    case_sensitive: bool = False,
    limit: int = 20,
    search_mode: str = "hybrid",
) -> dict[str, Any]:
    """
    Search schemas by keyword and/or semantic similarity.

    Args:
        query: Search query
        schemas_dir: Path to the schemas directory
        domain: Optional domain filter
        case_sensitive: Case-sensitive search (keyword mode only)
        limit: Maximum results to return
        search_mode: 'keyword', 'semantic', or 'hybrid' (default)

    Returns:
        Dictionary with matching schemas, excerpts, and relevance scores
    """
    if search_mode == "keyword":
        return _search_keyword(query, schemas_dir, domain, case_sensitive, limit)
    elif search_mode == "semantic":
        return _search_semantic(query, schemas_dir, domain, limit)
    else:  # hybrid (default)
        return _search_hybrid(query, schemas_dir, domain, case_sensitive, limit)


def _search_keyword(
    query: str,
    schemas_dir: str,
    domain: Optional[str] = None,
    case_sensitive: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Original keyword-based search using lexical matching.

    Uses intelligent search strategy:
    1. Exact phrase match (highest priority)
    2. All words present (AND logic)
    3. Any words present (OR logic) - ranked by relevance
    """
    schemas_path = Path(schemas_dir)
    all_candidates: list[tuple[dict[str, Any], int]] = []

    # Split query into words for multi-word search
    query_words = query.split()
    if not query_words:
        return {
            "query": query,
            "matches": [],
            "total": 0,
            "search_strategy": "empty_query",
            "search_mode": "keyword",
        }

    # Normalize query words for case-insensitive search
    search_words = query_words if case_sensitive else [w.lower() for w in query_words]
    search_query = query if case_sensitive else query.lower()

    # Get domain filter from index if specified
    domain_schemas = _get_domain_schemas(schemas_dir, domain)

    # Search in main directory
    for schema_file in schemas_path.glob("*.md"):
        if schema_file.name == "SCHEMA_INDEX.md":
            continue

        schema_name = schema_file.stem

        # Check domain filter
        if domain_schemas and schema_name not in domain_schemas:
            continue

        # Search in filename
        search_filename = schema_file.name if case_sensitive else schema_file.name.lower()
        filename_match_count = sum(1 for word in search_words if word in search_filename)
        exact_phrase_in_filename = search_query in search_filename
        all_words_in_filename = all(word in search_filename for word in search_words)

        # Search in content
        try:
            content = schema_file.read_text(encoding="utf-8")
            search_content = content if case_sensitive else content.lower()

            # Count word matches in content
            word_matches_in_content = [word for word in search_words if word in search_content]
            match_count = len(word_matches_in_content)
            exact_phrase_in_content = search_query in search_content
            all_words_in_content = match_count == len(search_words)

            # Calculate relevance score
            relevance = 0
            match_type = "none"

            # Highest priority: exact phrase match
            if exact_phrase_in_content or exact_phrase_in_filename:
                relevance = 1000 + match_count * 10
                match_type = "exact_phrase"
            # High priority: all words present (AND logic)
            elif all_words_in_content or all_words_in_filename:
                relevance = 500 + match_count * 10
                match_type = "all_words"
            # Medium priority: most words present
            elif match_count > 0:
                match_percentage = (match_count / len(search_words)) * 100
                relevance = int(match_percentage * 5) + match_count
                match_type = "partial"

            # Add filename bonus
            if filename_match_count > 0:
                relevance += filename_match_count * 5

            if relevance > 0:
                excerpt = _find_excerpt(content, query, search_words, case_sensitive)
                all_candidates.append(
                    (
                        {
                            "schema_name": schema_file.name,
                            "excerpt": excerpt,
                            "matched_in_filename": filename_match_count > 0,
                            "match_type": match_type,
                            "words_matched": match_count,
                            "total_words": len(search_words),
                        },
                        relevance,
                    )
                )
        except Exception:
            continue

    # Sort by relevance and take top results
    all_candidates.sort(key=lambda x: x[1], reverse=True)
    matches = [match for match, _ in all_candidates[:limit]]

    # Determine search strategy
    if matches:
        if any(m.get("match_type") == "exact_phrase" for m in matches):
            strategy = "exact_phrase"
        elif any(m.get("match_type") == "all_words" for m in matches):
            strategy = "all_words"
        else:
            strategy = "partial_words"
    else:
        strategy = "no_matches"

    return {
        "query": query,
        "matches": matches,
        "total": len(all_candidates),
        "search_strategy": strategy,
        "search_mode": "keyword",
        "showing": len(matches),
    }


def _search_semantic(
    query: str,
    schemas_dir: str,
    domain: Optional[str] = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Semantic search using sentence-transformers embeddings.

    Falls back to keyword search if sentence-transformers is not installed.
    """
    try:
        from schema_mcp.services.embedding_service import EmbeddingService
    except ImportError:
        # Fallback to keyword search if sentence-transformers not available
        result = _search_keyword(query, schemas_dir, domain, False, limit)
        result["search_mode"] = "semantic"
        result["fallback"] = "keyword (sentence-transformers not installed)"
        return result

    schemas_path = Path(schemas_dir)
    service = EmbeddingService(schemas_dir)

    # Get semantic similarities
    similarities = service.search_semantic(query, top_k=limit * 2)

    # Get domain filter if specified
    domain_schemas = _get_domain_schemas(schemas_dir, domain)

    matches = []
    for schema_name, similarity in similarities:
        # Apply domain filter
        schema_stem = schema_name.removesuffix(".md")
        if domain_schemas and schema_stem not in domain_schemas:
            continue

        # Read content for excerpt
        schema_file = schemas_path / schema_name
        try:
            content = schema_file.read_text(encoding="utf-8")
            excerpt = _find_excerpt_semantic(content)
        except Exception:
            excerpt = ""

        matches.append(
            {
                "schema_name": schema_name,
                "excerpt": excerpt,
                "scores": {
                    "semantic": round(similarity, 4),
                },
            }
        )

        if len(matches) >= limit:
            break

    return {
        "query": query,
        "matches": matches,
        "total": len(matches),
        "search_mode": "semantic",
        "showing": len(matches),
    }


def _search_hybrid(
    query: str,
    schemas_dir: str,
    domain: Optional[str] = None,
    case_sensitive: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Hybrid search combining semantic and keyword scores.

    Combined score = 0.7 * semantic + 0.3 * keyword_normalized

    Falls back to keyword search if sentence-transformers is not installed.
    """
    try:
        from schema_mcp.services.embedding_service import EmbeddingService
    except ImportError:
        # Fallback to keyword search if sentence-transformers not available
        result = _search_keyword(query, schemas_dir, domain, case_sensitive, limit)
        result["search_mode"] = "hybrid"
        result["fallback"] = "keyword (sentence-transformers not installed)"
        return result

    schemas_path = Path(schemas_dir)
    service = EmbeddingService(schemas_dir)

    # Get semantic similarities
    semantic_results = dict(service.search_semantic(query, top_k=100))

    # Get keyword scores
    keyword_results = _search_keyword(query, schemas_dir, domain, case_sensitive, limit=100)
    keyword_scores = {}
    max_keyword_score = 0

    for match in keyword_results["matches"]:
        schema_name = match["schema_name"]
        # Calculate normalized keyword score (0-1)
        words_matched = match.get("words_matched", 0)
        total_words = match.get("total_words", 1)
        score = words_matched / max(total_words, 1)
        # Boost for filename matches
        if match.get("matched_in_filename"):
            score = min(1.0, score + 0.2)
        keyword_scores[schema_name] = score
        max_keyword_score = max(max_keyword_score, score)

    # Normalize keyword scores
    if max_keyword_score > 0:
        keyword_scores = {k: v / max_keyword_score for k, v in keyword_scores.items()}

    # Combine scores for all schemas
    all_schemas = set(semantic_results.keys()) | set(keyword_scores.keys())
    domain_schemas = _get_domain_schemas(schemas_dir, domain)

    combined_results = []
    for schema_name in all_schemas:
        # Apply domain filter
        schema_stem = schema_name.removesuffix(".md")
        if domain_schemas and schema_stem not in domain_schemas:
            continue

        semantic_score = semantic_results.get(schema_name, 0.0)
        keyword_score = keyword_scores.get(schema_name, 0.0)
        combined_score = SEMANTIC_WEIGHT * semantic_score + KEYWORD_WEIGHT * keyword_score

        combined_results.append((schema_name, semantic_score, keyword_score, combined_score))

    # Sort by combined score
    combined_results.sort(key=lambda x: x[3], reverse=True)

    # Build response
    matches = []
    for schema_name, sem_score, kw_score, comb_score in combined_results[:limit]:
        schema_file = schemas_path / schema_name
        try:
            content = schema_file.read_text(encoding="utf-8")
            query_words = query.split()
            search_words = query_words if case_sensitive else [w.lower() for w in query_words]
            excerpt = _find_excerpt(content, query, search_words, case_sensitive)
        except Exception:
            excerpt = ""

        matches.append(
            {
                "schema_name": schema_name,
                "excerpt": excerpt,
                "scores": {
                    "semantic": round(sem_score, 4),
                    "keyword": round(kw_score, 4),
                    "combined": round(comb_score, 4),
                },
            }
        )

    return {
        "query": query,
        "matches": matches,
        "total": len(combined_results),
        "search_mode": "hybrid",
        "showing": len(matches),
    }


def _get_domain_schemas(schemas_dir: str, domain: Optional[str]) -> Optional[list[str]]:
    """Get list of schema names for a specific domain."""
    if not domain:
        return None

    from schema_mcp.tools.schema_index import parse_index

    index_data = parse_index(schemas_dir)
    for domain_data in index_data["domains"]:
        if domain_data["name"] == domain:
            return [s["file"].removesuffix(".md") for s in domain_data["schemas"]]
    return None


def _find_excerpt(
    content: str,
    query: str,
    search_words: list[str],
    case_sensitive: bool,
    context_chars: int = 100,
) -> str:
    """Find an excerpt around the first match of query in content."""
    search_content = content if case_sensitive else content.lower()
    search_query = query if case_sensitive else query.lower()

    # Try exact phrase first
    index = search_content.find(search_query)
    if index == -1:
        # Try first word
        for word in search_words:
            search_word = word if case_sensitive else word.lower()
            index = search_content.find(search_word)
            if index != -1:
                break

    if index == -1:
        # Return first part of content
        return content[: context_chars * 2] + "..." if len(content) > context_chars * 2 else content

    # Extract context around match
    start = max(0, index - context_chars)
    end = min(len(content), index + len(query) + context_chars)

    excerpt = content[start:end]
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(content):
        excerpt = excerpt + "..."

    return excerpt


def _find_excerpt_semantic(content: str, context_chars: int = 200) -> str:
    """Find excerpt for semantic search (first meaningful chunk)."""
    # Skip title line if present
    lines = content.split("\n")
    start_idx = 0
    for i, line in enumerate(lines):
        if line.strip() and not line.startswith("#"):
            start_idx = i
            break

    text = "\n".join(lines[start_idx:])
    if len(text) > context_chars:
        return text[:context_chars] + "..."
    return text
