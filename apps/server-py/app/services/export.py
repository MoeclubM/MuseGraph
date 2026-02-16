import io
import json


async def export_project(project, format: str) -> tuple[bytes, str, str]:
    """Export project content in the specified format.
    Returns (content_bytes, content_type, filename).
    """
    title = project.title or "untitled"
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()[:50]

    if format == "txt":
        content = (project.content or "").encode("utf-8")
        return content, "text/plain; charset=utf-8", f"{safe_title}.txt"

    elif format == "json":
        data = {
            "title": project.title,
            "description": project.description,
            "content": project.content,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
        }
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        return content, "application/json; charset=utf-8", f"{safe_title}.json"

    elif format == "md":
        lines = [f"# {project.title}", ""]
        if project.description:
            lines.extend([project.description, ""])
        lines.extend(["---", "", project.content or ""])
        content = "\n".join(lines).encode("utf-8")
        return content, "text/markdown; charset=utf-8", f"{safe_title}.md"

    elif format == "html":
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{project.title}</title></head>
<body><h1>{project.title}</h1>
{f'<p><em>{project.description}</em></p>' if project.description else ''}
<div>{(project.content or '').replace(chr(10), '<br>')}</div>
</body></html>"""
        content = html.encode("utf-8")
        return content, "text/html; charset=utf-8", f"{safe_title}.html"

    else:
        raise ValueError(f"Unsupported format: {format}")
