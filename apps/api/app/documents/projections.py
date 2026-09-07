from collections.abc import Sequence

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.documents.models import Document, DocumentLink, DocumentVersion
from app.documents.review import is_released
from app.documents.schemas import DocumentLinkResponse, DocumentResponse, DocumentVersionResponse

type DocumentAggregate = tuple[
    DocumentResponse, Sequence[DocumentVersionResponse], Sequence[DocumentLinkResponse]
]


def protected_aggregate(
    context: RequestContext,
    document: Document,
    versions: Sequence[DocumentVersion],
    links: Sequence[DocumentLink],
) -> DocumentAggregate:
    privileged = Permission.PROFIT_READ in context.permissions
    projected_versions = []
    title_visible = privileged
    for version in versions:
        released = is_released(document, version)
        visible = privileged or released
        title_visible = title_visible or released
        projected = DocumentVersionResponse.model_validate(version)
        projected.content_visible = visible
        projected.released = released
        if not visible:
            projected.file_name = None
            projected.mime_type = None
        # Scan failure text is not part of the reviewed file content.
        if not privileged:
            projected.rejected_reason = None
        projected_versions.append(projected)
    projected_links = [DocumentLinkResponse.model_validate(link) for link in links]
    result = DocumentResponse.model_validate(document)
    if not title_visible:
        result.title = None
    result.versions = projected_versions
    result.links = projected_links
    return result, projected_versions, projected_links
