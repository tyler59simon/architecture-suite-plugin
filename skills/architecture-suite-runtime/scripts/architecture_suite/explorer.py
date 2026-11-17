"""A self-contained read-only architecture explorer."""

import base64
import hashlib
import json
from .renderers import diagram_specs, render_svg
from .scenarios import scenario_scene
from .emit import render_scene_svg


def explorer_html(model, scenarios=None, diff=None):
    diagrams = [
        {"name": base, "svg": render_svg(model, view)}
        for base, view in diagram_specs(model, ["all"])
    ]
    diagrams.extend(
        {
            "name": "Scenario: " + s["name"],
            "svg": render_scene_svg(scenario_scene(s, model)),
        }
        for s in scenarios or []
    )
    payload = json.dumps(
        {"model": model, "diagrams": diagrams, "diff": diff or {}}, ensure_ascii=True
    ).replace("<", "\\u003c")
    head = (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:"><title>Architecture explorer</title><style>body{font:16px system-ui;margin:24px;color:#172b4d}input,select,button{font:inherit;padding:8px;margin:4px}main{display:grid;grid-template-columns:300px 1fr;gap:24px}#diagram{overflow:auto;max-height:75vh;border:1px solid #ccc}#diagram svg{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}button{display:block;text-align:left}details{margin:8px}#details{border-top:1px solid #ccc}</style><h1>Architecture explorer</h1><label>Search <input id="search" type="search"></label><label>Type <select id="type"><option value="">All</option></select></label><label>View <select id="view"></select></label><main><nav aria-label="Architecture elements" id="elements"></nav><section><div id="diagram" tabindex="0" aria-label="Diagram"></div><section id="details" aria-live="polite"></section><details><summary>Assumptions and gaps</summary><pre id="gaps"></pre></details><details><summary>Architecture changes</summary><pre id="changes"></pre></details></section></main><script>"""
    )
    script = (
        "const data="
        + payload
        + """;const $=id=>document.getElementById(id);function text(parent,tag,value){const e=document.createElement(tag);e.textContent=value;parent.append(e);return e}function select(e){$('details').replaceChildren();text($('details'),'h2',e.name);text($('details'),'pre',JSON.stringify(e,null,2));for(const id of e.evidence_ids||[]){const ev=data.model.evidence.find(v=>v.id===id);if(ev)text($('details'),'pre',JSON.stringify(ev,null,2))}const v=data.model.views.find(v=>v.boundary_id===e.id);if(v){const opt=[...$('view').options].find(o=>o.textContent.endsWith('/'+v.id));if(opt){$('view').value=opt.value;show()}}}function list(){const q=$('search').value.toLowerCase(),type=$('type').value;$('elements').replaceChildren();const visible=data.model.elements.filter(e=>(!type||e.type===type)&&JSON.stringify(e).toLowerCase().includes(q));function children(parent,root){for(const e of visible.filter(e=>e.parent_id===parent)){const d=document.createElement('details');d.open=!!q;const summary=text(d,'summary',e.name);summary.tabIndex=0;const b=text(d,'button','Inspect '+e.name);b.onclick=()=>select(e);root.append(d);children(e.id,d)}}children(undefined,$('elements'));for(const e of visible.filter(e=>e.parent_id&&!visible.some(p=>p.id===e.parent_id))){const b=text($('elements'),'button',e.name);b.onclick=()=>select(e)}}function show(){$('diagram').innerHTML=data.diagrams[Number($('view').value)].svg}for(const t of new Set(data.model.elements.map(e=>e.type))){const o=text($('type'),'option',t);o.value=t}data.diagrams.forEach((d,i)=>{const o=text($('view'),'option',d.name);o.value=i});$('search').oninput=list;$('type').onchange=list;$('view').onchange=show;$('gaps').textContent=JSON.stringify({assumptions:data.model.assumptions,gaps:data.model.gaps},null,2);$('changes').textContent=JSON.stringify(data.diff,null,2);list();show();"""
    )
    # Allow exactly this file's script: injected markup can never run handlers or scripts.
    digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode()
    head = head.replace("script-src 'unsafe-inline'", f"script-src 'sha256-{digest}'")
    return head + script + "</script></html>"
