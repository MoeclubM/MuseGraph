import io
import json


def _resolve_export_content(project) -> str:
    chapters = sorted(getattr(project, "chapters", []) or [], key=lambda c: (getattr(c, "order_index", 0), getattr(c, "created_at", 0)))
    return "\n\n".join((chapter.content or "") for chapter in chapters if chapter.content is not None)


async def export_project(project, format: str) -> tuple[bytes, str, str]:
    """Export project content in the specified format.
    Returns (content_bytes, content_type, filename).
    """
    title = project.title or "untitled"
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()[:50]

    if format == "txt":
        content_text = _resolve_export_content(project)
        content = content_text.encode("utf-8")
        return content, "text/plain; charset=utf-8", f"{safe_title}.txt"

    elif format == "json":
        content_text = _resolve_export_content(project)
        data = {
            "title": project.title,
            "description": project.description,
            "content": content_text,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
        }
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        return content, "application/json; charset=utf-8", f"{safe_title}.json"

    elif format == "md":
        content_text = _resolve_export_content(project)
        lines = [f"# {project.title}", ""]
        if project.description:
            lines.extend([project.description, ""])
        lines.extend(["---", "", content_text])
        content = "\n".join(lines).encode("utf-8")
        return content, "text/markdown; charset=utf-8", f"{safe_title}.md"

    elif format == "html":
        content_text = _resolve_export_content(project)
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{project.title}</title></head>
<body><h1>{project.title}</h1>
{f'<p><em>{project.description}</em></p>' if project.description else ''}
<div>{content_text.replace(chr(10), '<br>')}</div>
</body></html>"""
        content = html.encode("utf-8")
        return content, "text/html; charset=utf-8", f"{safe_title}.html"

    else:
        raise ValueError(f"Unsupported format: {format}")
