"""Generate a single-file, self-contained HTML report from an export CSV.

    python src/report.py [csv_path] [--out report.html]

No external assets/CDN — the .html opens offline in any browser and is easy to email/share.
Interactive: search box, keyword/city/seller-type filters, and click-to-sort columns.
"""
from __future__ import annotations

import argparse
import csv
import html as _html
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import settings   # noqa: E402
import relevance  # noqa: E402


def _read_rows(csv_path: Path):
    """Return (rows, column_names) preserving the CSV column order."""
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        cols = reader.fieldnames or (list(rows[0].keys()) if rows else [])
    return rows, cols


def _raw_table_html(rows: list[dict], cols: list[str]) -> str:
    """A full table mirroring the CSV: every column, every row (server-rendered)."""
    head = "".join(f"<th>{_html.escape(c)}</th>" for c in cols)
    body = []
    for r in rows:
        tds = []
        for c in cols:
            v = r.get(c) or ""
            if c in ("product_url", "shop_url") and v:
                v_esc = _html.escape(v)
                tds.append(f'<td><a href="{v_esc}" target="_blank" rel="noopener">{v_esc}</a></td>')
            else:
                tds.append(f"<td>{_html.escape(str(v))}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    return (f'<div class="rawwrap"><table class="raw"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def _num(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def _sold(r: dict):
    ex = _num(r.get("sold_count_exact"))
    return ex if ex is not None else _num(r.get("sold_count"))


def _load_filters():
    return relevance.load_filters()


def _is_noise(name: str, excl=None, req=None) -> bool:
    return relevance.is_noise(name)


def _rupiah(n) -> str:
    return "Rp" + format(int(n), ",").replace(",", ".") if n is not None else "-"


def _summary(rows: list[dict]) -> dict:
    agg: dict = {}
    for r in rows:
        key = (r.get("keyword", ""), r.get("is_official") == "1")
        a = agg.setdefault(key, {"n": 0, "sold": 0, "psum": 0, "pn": 0})
        a["n"] += 1
        a["sold"] += _sold(r) or 0
        p = _num(r.get("price"))
        if p:
            a["psum"] += p
            a["pn"] += 1
    return agg


def _cards_html(rows: list[dict]) -> str:
    total = len(rows)
    relevant = sum(1 for r in rows if not r.get("_noise"))
    off = sum(1 for r in rows if r.get("is_official") == "1")
    non = total - off
    sold_non = sum(_sold(r) or 0 for r in rows if r.get("is_official") != "1")
    kws = sorted({r.get("keyword", "") for r in rows})
    cities = sorted({r.get("city", "") for r in rows})

    def card(label, value):
        return (f'<div class="card"><div class="card-v">{_html.escape(str(value))}</div>'
                f'<div class="card-l">{_html.escape(label)}</div></div>')

    return (
        card("Products (total)", total)
        + card("Relevant (filtered)", relevant)
        + card("Noise removed", total - relevant)
        + card("Non-official sellers", non)
        + card("Sold (non-official)", format(sold_non, ",").replace(",", "."))
        + card("Keywords", ", ".join(k for k in kws if k))
        + card("Cities", ", ".join(c for c in cities if c))
    )


def _summary_table_html(rows: list[dict]) -> str:
    agg = _summary(rows)
    body = []
    for (kw, is_off), a in sorted(agg.items(), key=lambda x: (x[0][0], not x[0][1])):
        avg = a["psum"] // a["pn"] if a["pn"] else 0
        typ = "Official" if is_off else "Non-official"
        cls = "off" if is_off else "non"
        body.append(
            f"<tr><td>{_html.escape(kw)}</td>"
            f'<td><span class="badge {cls}">{typ}</span></td>'
            f'<td class="r">{a["n"]}</td>'
            f'<td class="r">{format(a["sold"], ",").replace(",", ".")}</td>'
            f'<td class="r">{_rupiah(avg)}</td></tr>'
        )
    return (
        "<table class='sum'><thead><tr><th>Keyword</th><th>Type</th>"
        "<th class='r'>#Products</th><th class='r'>Total sold</th>"
        "<th class='r'>Avg price</th></tr></thead><tbody>"
        + "".join(body) + "</tbody></table>"
    )


def _sellers_html(rows: list[dict]):
    """Seller-level rollup of REAL IQOS products (relevant only, deduped by product_id)."""
    per_product = {}
    for r in rows:
        if r.get("_noise"):
            continue
        pid = r.get("product_id")
        if not pid:
            continue
        s = _sold(r) or 0
        prev = per_product.get(pid)
        if prev is None or s > prev["sold"]:
            per_product[pid] = {
                "key": r.get("shop_id") or r.get("shop_name"),
                "shop": r.get("shop_name"), "city": r.get("shop_city"),
                "off": r.get("is_official") == "1", "sold": s,
            }
    sellers = {}
    for p in per_product.values():
        d = sellers.setdefault(p["key"], {"shop": p["shop"], "city": p["city"],
                                          "off": False, "n": 0, "sold": 0})
        d["n"] += 1
        d["sold"] += p["sold"]
        d["off"] = d["off"] or p["off"]
    ordered = sorted(sellers.values(), key=lambda d: (-d["sold"], -d["n"]))

    body = []
    for d in ordered:
        badge = ('<span class="badge off">Mall</span>' if d["off"]
                 else '<span class="badge non">seller</span>')
        sold = format(d["sold"], ",").replace(",", ".")
        body.append(
            f"<tr><td>{_html.escape(d['shop'] or '')}</td>"
            f"<td>{_html.escape(d['city'] or '')}</td>"
            f"<td>{badge}</td>"
            f"<td class='r'>{d['n']}</td>"
            f"<td class='r'>{sold}</td></tr>"
        )
    table = (
        "<table class='sum'><thead><tr><th>Seller</th><th>City</th><th>Type</th>"
        "<th class='r'>#Real products</th><th class='r'>Total sold</th></tr></thead>"
        "<tbody>" + "".join(body) + "</tbody></table>"
    )
    return table, len(ordered)


_CSS = """
:root{--bd:#e3e6ea;--mut:#667085;--off:#7c3aed;--non:#0d9488;--bg:#f7f8fa}
*{box-sizing:border-box}
body{margin:0;font:14px/1.45 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1a1f36;background:var(--bg)}
header{background:#0b1324;color:#fff;padding:22px 26px}
header h1{margin:0;font-size:20px}
header .meta{margin:6px 0 0;color:#9aa4b2;font-size:12px}
main{padding:22px 26px;max-width:1400px;margin:0 auto}
h2{font-size:15px;margin:26px 0 10px}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin-top:18px}
.card{background:#fff;border:1px solid var(--bd);border-radius:10px;padding:12px 16px;min-width:130px}
.card-v{font-size:20px;font-weight:600}
.card-l{color:var(--mut);font-size:12px;margin-top:2px}
table{border-collapse:collapse;width:100%;background:#fff;border:1px solid var(--bd);border-radius:10px;overflow:hidden}
th,td{padding:9px 12px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top}
th{background:#f0f2f5;font-size:12px;color:#344054;cursor:pointer;white-space:nowrap;position:sticky;top:0}
th.r,td.r{text-align:right}
tbody tr:nth-child(even){background:#fafbfc}
tbody tr:hover{background:#eef4ff}
a{color:#1d4ed8;text-decoration:none}a:hover{text-decoration:underline}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600;color:#fff}
.badge.off{background:var(--off)}.badge.non{background:var(--non)}
.controls{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.controls input,.controls select{padding:8px 10px;border:1px solid var(--bd);border-radius:8px;font-size:13px;background:#fff}
.controls input{flex:1;min-width:220px}
.controls .chk{display:flex;align-items:center;gap:6px;font-size:13px;color:#344054;padding:8px 4px}
.controls .chk input{flex:0}
.sum td,.sum th{white-space:nowrap}
#count{color:var(--mut);font-size:12px;margin-left:auto;align-self:center}
.foot{color:var(--mut);font-size:11px;margin:24px 0 8px}
.rawwrap{overflow-x:auto;max-height:70vh;overflow-y:auto;border:1px solid var(--bd);border-radius:10px}
.raw{border:0;border-radius:0}
.raw th,.raw td{white-space:nowrap;font-size:12px;max-width:340px;overflow:hidden;text-overflow:ellipsis}
details>summary{cursor:pointer;font-size:15px;font-weight:600;margin:26px 0 10px}
"""

_JS = r"""
const DATA = /*__DATA__*/[];
DATA.forEach(r => {
  r._sold = (r.sold_count_exact && r.sold_count_exact!=="") ? +r.sold_count_exact : (+r.sold_count||0);
  r._off  = r.is_official === "1";
});
const cols = [
  {k:"rank",t:"#",n:true},
  {k:"keyword",t:"Keyword"},
  {k:"city",t:"City"},
  {k:"name",t:"Product",link:"product_url"},
  {k:"price",t:"Price",n:true,rp:true},
  {k:"_sold",t:"Sold",n:true,label:"sold_label"},
  {k:"rating",t:"Rating",n:true},
  {k:"shop_name",t:"Seller",link:"shop_url"},
  {k:"shop_id",t:"Seller ID"},
  {k:"_off",t:"Type"},
];
let sortK="_sold", sortDir=-1;
const $=s=>document.querySelector(s);
const rp=n=>"Rp"+(""+ (n||0)).replace(/\B(?=(\d{3})+(?!\d))/g,".");
const esc=s=>s==null?"":s;

function opts(sel,vals){vals.forEach(v=>{if(!v)return;const o=document.createElement("option");o.value=v;o.textContent=v;sel.appendChild(o);});}
opts($("#fKeyword"),[...new Set(DATA.map(r=>r.keyword))].sort());
opts($("#fCity"),[...new Set(DATA.map(r=>r.city))].sort());

function thead(){
  const tr=$("#thead"); tr.innerHTML="";
  cols.forEach(c=>{const th=document.createElement("th");if(c.n)th.className="r";
    th.textContent=c.t+(sortK===c.k?(sortDir<0?" ▼":" ▲"):"");
    th.onclick=()=>{if(sortK===c.k)sortDir*=-1;else{sortK=c.k;sortDir=c.n?-1:1;}render();};
    tr.appendChild(th);});
}
function render(){
  const q=$("#q").value.toLowerCase(), fk=$("#fKeyword").value, fc=$("#fCity").value, ft=$("#fType").value;
  const relOnly=$("#relevantOnly").checked;
  let rows=DATA.filter(r=>{
    if(relOnly&&r._noise)return false;
    if(fk&&r.keyword!==fk)return false;
    if(fc&&r.city!==fc)return false;
    if(ft==="off"&&!r._off)return false;
    if(ft==="non"&&r._off)return false;
    if(q){const hay=(r.name+" "+r.shop_name+" "+r.shop_id).toLowerCase();if(!hay.includes(q))return false;}
    return true;
  });
  rows.sort((a,b)=>{let x=a[sortK],y=b[sortK];
    if(cols.find(c=>c.k===sortK)?.n){x=+x||0;y=+y||0;return (x-y)*sortDir;}
    return (""+esc(x)).localeCompare(""+esc(y))*sortDir;});
  const tb=$("#tbody"); tb.innerHTML="";
  rows.forEach(r=>{
    const tr=document.createElement("tr");
    cols.forEach(c=>{
      const td=document.createElement("td"); if(c.n)td.className="r";
      if(c.k==="_off"){const s=document.createElement("span");s.className="badge "+(r._off?"off":"non");s.textContent=r._off?"Official":"Seller";td.appendChild(s);}
      else if(c.k==="price"){td.textContent=rp(r.price);}
      else if(c.k==="_sold"){td.textContent=(r._sold||0).toLocaleString("id-ID");if(r.sold_label){td.title=r.sold_label;}}
      else if(c.link&&r[c.link]){const a=document.createElement("a");a.href=r[c.link];a.target="_blank";a.rel="noopener";a.textContent=esc(r[c.k]);td.appendChild(a);}
      else td.textContent=esc(r[c.k]);
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
  $("#count").textContent=rows.length+" / "+DATA.length+" rows";
  thead();
}
["#q","#fKeyword","#fCity","#fType","#relevantOnly"].forEach(s=>$(s).addEventListener("input",render));
render();
"""


def generate_report(csv_path, out_path=None) -> Path:
    csv_path = Path(csv_path)
    rows, cols = _read_rows(csv_path)
    excl, req = _load_filters()
    for r in rows:
        r["_noise"] = _is_noise(r.get("name", ""), excl, req)
    out_path = Path(out_path) if out_path else csv_path.with_suffix(".html")

    data_json = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    meta = (f"Generated {ts} &middot; Source: {_html.escape(csv_path.name)} "
            f"&middot; {len(rows)} products")
    rawtable = _raw_table_html(rows, cols)
    rawcount = len(rows)
    sellers_html, n_sellers = _sellers_html(rows)

    doc = f"""<!DOCTYPE html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tokopedia IQOS POC - Sold Report</title>
<style>{_CSS}</style></head>
<body>
<header>
  <h1>Tokopedia IQOS &mdash; Competitor Sold Report</h1>
  <div class="meta">{meta}</div>
</header>
<main>
  <div class="cards">{_cards_html(rows)}</div>

  <h2>Official vs Non-official (by keyword)</h2>
  {_summary_table_html(rows)}

  <h2>Sellers of real IQOS products ({n_sellers})</h2>
  {sellers_html}

  <h2>Products</h2>
  <div class="controls">
    <input id="q" placeholder="Search product / seller / seller id...">
    <select id="fKeyword"><option value="">All keywords</option></select>
    <select id="fCity"><option value="">All cities</option></select>
    <select id="fType">
      <option value="">All sellers</option>
      <option value="non">Non-official only</option>
      <option value="off">Official only</option>
    </select>
    <label class="chk"><input type="checkbox" id="relevantOnly" checked> Relevant only (hide noise)</label>
    <span id="count"></span>
  </div>
  <table><thead><tr id="thead"></tr></thead><tbody id="tbody"></tbody></table>

  <details open>
    <summary>Raw data (all columns, {rawcount} rows) &mdash; mirrors the CSV</summary>
    {rawtable}
  </details>

  <div class="foot">Tokopedia IQOS scraper PoC &middot; sold counts are Tokopedia's own
  transaction tally (bucketed for high-volume sellers). Data is a point-in-time snapshot.</div>
</main>
<script>{_JS.replace("/*__DATA__*/", data_json)}</script>
</body></html>"""

    out_path.write_text(doc, encoding="utf-8")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Build a single-file HTML report from an export CSV")
    ap.add_argument("csv", nargs="?", help="path to export CSV (default: newest data/export_*.csv)")
    ap.add_argument("--out", default=None, help="output HTML path")
    args = ap.parse_args()

    csv_path = args.csv
    if not csv_path:
        exports = sorted(settings.DATA_DIR.glob("export_*.csv"))
        if not exports:
            raise SystemExit("No export_*.csv found in data/. Run the scraper first.")
        csv_path = exports[-1]
    out = generate_report(csv_path, args.out)
    print(f"Report written: {out}")


if __name__ == "__main__":
    main()
