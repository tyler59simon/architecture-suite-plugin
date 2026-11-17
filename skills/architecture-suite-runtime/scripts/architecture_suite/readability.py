"""Transparent layout diagnostics; density never removes content."""

from .scene import Scene


def readability_findings(scene: Scene) -> list[dict]:
    metrics = score_scene(scene)
    findings = []
    if metrics["crossings"] > max(1, len(scene.edges)) * 1.5:
        findings.append({"code": "readability-crossings", "elements": []})
    if metrics["bends"] > max(1, len(scene.edges)) * 6:
        findings.append({"code": "readability-bends", "elements": []})
    if metrics["aspect_ratio"] > 12 and len(scene.boxes) > 1:
        findings.append({"code": "readability-aspect", "elements": []})
    def distance(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    for edge in scene.edges:
        if len(edge.points) > 1:
            route = sum(distance(a, b) for a, b in zip(edge.points, edge.points[1:]))
            direct = distance(edge.points[0], edge.points[-1])
            if route > max(600, direct * 6):
                findings.append({"code": "readability-detour", "elements": [edge.id]})
    return findings


def score_scene(scene: Scene) -> dict:
    crossings = 0
    segments = [
        (edge.id, a, b)
        for edge in scene.edges
        for a, b in zip(edge.points, edge.points[1:])
    ]
    for i, (ident, a, b) in enumerate(segments):
        for other, c, d in segments[i + 1 :]:
            if ident == other:
                continue
            if (
                a[0] == b[0]
                and c[1] == d[1]
                and min(c[0], d[0]) < a[0] < max(c[0], d[0])
                and min(a[1], b[1]) < c[1] < max(a[1], b[1])
            ):
                crossings += 1
            elif (
                a[1] == b[1]
                and c[0] == d[0]
                and min(a[0], b[0]) < c[0] < max(a[0], b[0])
                and min(c[1], d[1]) < a[1] < max(c[1], d[1])
            ):
                crossings += 1
    bends = sum(max(0, len(e.points) - 2) for e in scene.edges)
    aspect = max(scene.width / scene.height, scene.height / scene.width)
    advisories = []
    if len(scene.boxes) > 35 or len(scene.edges) > 50:
        advisories.append("Dense view; split by scope or use small-multiples")
    if aspect > 5:
        advisories.append("Long page; consider a different direction")
    return {
        "crossings": crossings,
        "bends": bends,
        "aspect_ratio": round(aspect, 3),
        "score": crossings * 100 + bends * 3 + aspect,
        "advisories": advisories,
    }
