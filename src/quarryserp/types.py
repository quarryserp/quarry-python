"""Public API response types. Response keys preserve their camelCase spelling."""

from typing import Dict, List, Literal, Optional, TypedDict

ResolveLinksMode = Literal["organic", "all", "none"]
V1SearchType = Literal["web", "news", "videos", "images", "shopping", "places"]
V1Status = Literal["pending", "completed", "failed"]
SearchType = V1SearchType
SearchMode = Literal["sync", "async"]
ResolveLinks = ResolveLinksMode
ImageFallback = Literal["none", "page"]

V1ErrorCode = Literal[
    "INVALID_PARAMETER",
    "INVALID_CURSOR",
    "UNAUTHORIZED",
    "NOT_FOUND",
    "BLOCKED_BY_CAPTCHA",
    "FORBIDDEN",
    "QUOTA_EXCEEDED",
    "RATE_LIMITED",
    "INTERNAL_ERROR",
]
ClientErrorCode = Literal[
    "INVALID_PARAMETER",
    "INVALID_CURSOR",
    "UNAUTHORIZED",
    "NOT_FOUND",
    "BLOCKED_BY_CAPTCHA",
    "FORBIDDEN",
    "QUOTA_EXCEEDED",
    "RATE_LIMITED",
    "INTERNAL_ERROR",
    "NETWORK_ERROR",
]


class V1Error(TypedDict):
    """V1Error API fields."""

    code: V1ErrorCode
    message: str
    retryable: bool


class _V1QueryRequired(TypedDict):
    text: str
    type: V1SearchType
    engine: Literal["google"]


class V1Query(_V1QueryRequired, total=False):
    """V1Query API fields."""

    lang: str
    country: str
    sourceUrl: str


class _V1SitelinkRequired(TypedDict):
    title: str
    url: str


class V1Sitelink(_V1SitelinkRequired, total=False):
    """V1Sitelink API fields."""

    snippet: str


class _V1OrganicRequired(TypedDict):
    rank: int
    title: str
    url: str


class V1Organic(_V1OrganicRequired, total=False):
    """V1Organic API fields."""

    displayUrl: str
    domain: str
    siteName: str
    snippet: str
    highlights: List[str]
    publishedAt: str
    publishedText: str
    faviconUrl: str
    sitelinks: List[V1Sitelink]


class _V1VideoRequired(TypedDict):
    rank: int
    title: str
    url: str


class V1Video(_V1VideoRequired, total=False):
    """V1Video API fields."""

    displayUrl: str
    source: str
    channel: str
    publishedAt: str
    publishedText: str
    snippet: str
    duration: str
    thumbnailUrl: str


class _V1ImageRequired(TypedDict):
    rank: int


class V1Image(_V1ImageRequired, total=False):
    """V1Image API fields."""

    title: str
    pageUrl: str
    source: str
    imageUrl: str
    imageUrlFrom: Literal["google", "page"]
    width: int
    height: int
    thumbnailUrl: str


class _V1ProductRequired(TypedDict):
    rank: int
    title: str


class V1Product(_V1ProductRequired, total=False):
    """V1Product API fields."""

    url: str
    source: str
    priceText: str
    price: float
    oldPriceText: str
    oldPrice: float
    rating: float
    reviews: int
    delivery: str
    thumbnailUrl: str


class _V1AiOverviewBlocksRequired(TypedDict):
    type: Literal["paragraph", "heading", "list"]


class V1AiOverviewBlocks(_V1AiOverviewBlocksRequired, total=False):
    """V1AiOverviewBlocks API fields."""

    text: str
    items: List[str]


class _V1AiOverviewReferencesRequired(TypedDict):
    title: str
    url: str


class V1AiOverviewReferences(_V1AiOverviewReferencesRequired, total=False):
    """V1AiOverviewReferences API fields."""

    source: str


class _V1AiOverviewRequired(TypedDict):
    text: str
    blocks: List[V1AiOverviewBlocks]


class V1AiOverview(_V1AiOverviewRequired, total=False):
    """V1AiOverview API fields."""

    references: List[V1AiOverviewReferences]


class _V1PlaceRequired(TypedDict):
    rank: int
    title: str


class V1Place(_V1PlaceRequired, total=False):
    """V1Place API fields."""

    placeId: str
    rating: float
    reviews: int
    price: str
    category: str
    address: str
    hours: str
    phone: str
    website: str
    mapsUrl: str
    thumbnailUrl: str


class _V1NewsRequired(TypedDict):
    rank: int
    title: str
    url: str


class V1News(_V1NewsRequired, total=False):
    """V1News API fields."""

    source: str
    publishedAt: str
    publishedText: str
    snippet: str
    thumbnailUrl: str


class _V1TopStoryRequired(TypedDict):
    title: str
    url: str


class V1TopStory(_V1TopStoryRequired, total=False):
    """V1TopStory API fields."""

    source: str
    publishedText: str
    thumbnailUrl: str


class _V1KnowledgePanelSourceRequired(TypedDict):
    name: str


class V1KnowledgePanelSource(_V1KnowledgePanelSourceRequired, total=False):
    """V1KnowledgePanelSource API fields."""

    url: str


class V1KnowledgePanelAttributes(TypedDict):
    """V1KnowledgePanelAttributes API fields."""

    label: str
    value: str


class V1KnowledgePanelRelatedEntities(TypedDict):
    """V1KnowledgePanelRelatedEntities API fields."""

    name: str
    searchUrl: str


class V1KnowledgePanelProfiles(TypedDict):
    """V1KnowledgePanelProfiles API fields."""

    name: str
    url: str


class _V1KnowledgePanelImagesRequired(TypedDict):
    pageUrl: str


class V1KnowledgePanelImages(_V1KnowledgePanelImagesRequired, total=False):
    """V1KnowledgePanelImages API fields."""

    thumbnailUrl: str


class _V1KnowledgePanelRequired(TypedDict):
    title: str


class V1KnowledgePanel(_V1KnowledgePanelRequired, total=False):
    """V1KnowledgePanel API fields."""

    type: str
    description: str
    source: V1KnowledgePanelSource
    attributes: List[V1KnowledgePanelAttributes]
    imageUrl: str
    relatedEntities: List[V1KnowledgePanelRelatedEntities]
    profiles: List[V1KnowledgePanelProfiles]
    images: List[V1KnowledgePanelImages]


class V1RelatedQuery(TypedDict):
    """V1RelatedQuery API fields."""

    query: str
    searchUrl: str


class _V1ResultsRequired(TypedDict):
    organic: List[V1Organic]
    questions: List[str]
    relatedQueries: List[V1RelatedQuery]


class V1Results(_V1ResultsRequired, total=False):
    """V1Results API fields."""

    news: List[V1News]
    videos: List[V1Video]
    images: List[V1Image]
    shopping: List[V1Product]
    places: List[V1Place]
    aiOverview: V1AiOverview
    topStories: List[V1TopStory]
    knowledgePanel: V1KnowledgePanel


class _V1PaginationRequired(TypedDict):
    hasNext: bool


class V1Pagination(_V1PaginationRequired, total=False):
    """V1Pagination API fields."""

    nextCursor: str
    prevCursor: str


class _V1MetaRequired(TypedDict):
    cached: bool
    createdAt: str


class V1Meta(_V1MetaRequired, total=False):
    """V1Meta API fields."""

    completedAt: str
    durationMs: float
    queueMs: float
    searchMs: float
    timings: Dict[str, float]
    htmlUrl: str
    warning: str


class _V1SearchRequired(TypedDict):
    id: str
    status: V1Status
    query: V1Query
    meta: V1Meta


class V1Search(_V1SearchRequired, total=False):
    """V1Search API fields."""

    results: V1Results
    pagination: V1Pagination
    pollUrl: str
    retryAfterMs: float
    error: V1Error


class _V1CursorRequired(TypedDict):
    v: Literal[1]
    query: str
    type: V1SearchType
    start: int
    resolveLinks: ResolveLinksMode


class V1Cursor(_V1CursorRequired, total=False):
    """V1Cursor API fields."""

    lang: str
    country: str


class V1AccountPlan(TypedDict):
    """V1AccountPlan API fields."""

    monthlyQuota: Optional[int]
    ratePerMinute: Optional[int]


class V1AccountUsage(TypedDict):
    """V1AccountUsage API fields."""

    month: str
    used: int
    remaining: Optional[int]


class V1Account(TypedDict):
    """V1Account API fields."""

    keyId: str
    name: str
    admin: bool
    plan: V1AccountPlan
    usage: V1AccountUsage
