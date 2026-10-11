(() => {
  if(location.hostname!=='sisetong.kr' && location.hostname!=='www.sisetong.kr') {
    alert('시세통 지도에서 실행해 주세요.'); return;
  }
  document.getElementById('sisepicker-web-panel')?.remove();
  const records=extractSisetong(document);
  const panel=document.createElement('div'); panel.id='sisepicker-web-panel';
  Object.assign(panel.style,{position:'fixed',right:'16px',top:'16px',width:'340px',maxHeight:'85vh',overflow:'auto',background:'white',color:'#111',padding:'16px',border:'2px solid #2563eb',borderRadius:'10px',zIndex:'2147483647',font:'14px sans-serif'});
  const title=document.createElement('strong'); title.textContent='SisePicker — 단지 선택'; panel.append(title);
  const close=document.createElement('button');close.textContent='닫기';close.onclick=()=>panel.remove();close.style.float='right';panel.append(close);
  const note=document.createElement('p');note.textContent=records.length?'값을 확인하고 복사한 뒤 SisePicker에서 Ctrl+V를 누르세요.':'연결할 수 있는 표가 없습니다. 지도를 확대하고 표가 보이게 해 주세요. 옮겨진 표나 중복 좌표는 제외됩니다.'; panel.append(note);
  for(const rec of records) {
    const section=document.createElement('div');section.style.cssText='border-top:1px solid #ddd;padding:12px 0';
    const name=document.createElement('strong');name.textContent=rec.name+' '+rec.year+'년';section.append(name);
    const preview=document.createElement('pre');preview.textContent=rec.areas.map((a,i)=>a+'㎡: 매매 '+rec.rows[0][i]+' / 전세 '+rec.rows[1][i]).join('\n');section.append(preview);
    const button=document.createElement('button');button.textContent='이 단지 복사';
    button.onclick=async()=>{
      const text='SISEPICKER_WEB_V1\n'+JSON.stringify(rec);
      try {await navigator.clipboard.writeText(text);button.textContent='복사됨 — SisePicker에서 Ctrl+V';}
      catch {const area=document.createElement('textarea');area.value=text;section.append(area);area.select();note.textContent='자동 복사가 차단됐습니다. 선택된 내용을 Ctrl+C로 복사해 주세요.';}
    };section.append(button);panel.append(section);
  }
  document.body.append(panel);
})();
