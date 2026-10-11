function extractSisetong(document) {
  const visible = e => { const r=e.getBoundingClientRect(); return r.width>0 && r.height>0 && r.right>0 && r.bottom>0 && r.left<innerWidth && r.top<innerHeight; };
  const anchor = e => { for(let p=e.parentElement;p;p=p.parentElement) if(p.style.position==='absolute' && p.style.left && p.style.top) return p; return null; };
  const heads=[], tables=[];
  for (const e of document.querySelectorAll('div')) {
    if(e.style.flexDirection!=='column' || !visible(e)) continue;
    const a=anchor(e); if(!a) continue;
    const children=Array.from(e.children);
    if(children.length===2 && children.every(c=>!c.children.length)) {
      const year=children[1].textContent.trim().match(/^(\d{2})y\s+\d+\^$/i);
      if(year) heads.push({a,name:children[0].textContent.trim(),year:year[1]});
    }
    if(children.length>=3 && children.length<=6 && children.every(r=>r.children.length>0)) {
      const rows=children.map(r=>Array.from(r.children,c=>c.textContent.trim()));
      const n=rows[0].length;
      if(n<=30 && rows.every(r=>r.length===n) && rows[0].every(v=>/^\d{2,3}$/.test(v)) &&
         rows.slice(1).every(r=>r.every(v=>/^-?\d+(\.\d+)?$|^-$/.test(v)))) tables.push({a,rows});
    }
  }
  const same=(a,b)=>a.parentElement===b.parentElement && a.style.left===b.style.left && a.style.top===b.style.top;
  const result=[];
  for(const h of heads) {
    const matches=tables.filter(t=>same(h.a,t.a));
    if(matches.length!==1 || heads.filter(x=>same(x.a,h.a)).length!==1) continue;
    const t=matches[0];
    result.push({source:'https://sisetong.kr/',name:h.name,year:h.year,areas:t.rows[0],rows:t.rows.slice(1)});
  }
  return result;
}
