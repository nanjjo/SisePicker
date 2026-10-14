/* Bookmarklet: only operates the visible Naver page's own filters and list. */
(async () => {
  if (location.hostname !== 'new.land.naver.com' || !/^\/complexes\/\d+/.test(location.pathname)) {
    alert('new.land.naver.com에서 단지를 선택한 뒤 실행하세요.'); return;
  }
  const old=document.getElementById('sisepicker-naver-panel');if(old){old.scrollIntoView();return;}
  const currentId=()=>location.pathname.match(/\/complexes\/(\d+)/)?.[1];
  let complexId=null;
  const panel=document.createElement('div');panel.id='sisepicker-naver-panel';
  // Panel clicks must not reach the site's outside-click filter closer.
  panel.onclick=event=>event.stopPropagation();
  panel.style.cssText='position:fixed;right:16px;top:90px;width:420px;max-height:80vh;overflow:auto;z-index:2147483647;background:white;color:#222;border:2px solid #03a65a;border-radius:10px;padding:16px;box-shadow:0 5px 25px #5558;font:14px/1.6 sans-serif';
  const title=document.createElement('strong');title.textContent='네이버 부동산 → SisePicker';
  const info=document.createElement('p');info.textContent='단지정보를 연 상태에서 시작하세요. 매매·전세, 전체동, 낮은가격순으로 바꾸고 목록을 읽습니다. 앱에서 전용/공급 면적과 40평 미만 기준을 선택합니다. 상단 가격·층 필터는 먼저 해제하세요. 수집 중에는 단지나 필터를 바꾸지 마세요.';
  const status=document.createElement('p'),preview=document.createElement('pre');preview.style.whiteSpace='pre-wrap';
  status.style.cssText='padding:12px;background:#fff0d4;font-weight:bold;border-radius:6px;white-space:pre-wrap';
  status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  status.textContent='대기 중 — 현재 선택한 단지의 수집 시작을 누르세요.';
  const progress=document.createElement('progress');progress.style.cssText='width:100%;height:16px;display:none';
  const start=document.createElement('button');start.textContent='매매·전세 수집 시작';
  const copy=document.createElement('button');copy.textContent='결과 복사';copy.disabled=true;
  const close=document.createElement('button');close.textContent='닫기 / 중지';
  for(const b of [start,copy,close])b.style.cssText='margin:4px;padding:8px;background:#e9f6ed;border:1px solid #83b98f;cursor:pointer';
  panel.append(title,info,start,copy,close,status,progress,preview);document.body.append(panel);
  let stopped=false,payload=null;
  close.onclick=()=>{stopped=true;panel.remove();};
  const guard=()=>{if(stopped)throw new Error('중지됨');if(location.pathname.match(/\/complexes\/(\d+)/)?.[1]!==complexId)throw new Error('단지가 바뀌었습니다. 새 단지에서 다시 실행하세요.');};
  const pause=async(ms)=>{await new Promise(r=>setTimeout(r,ms));guard();};
  const wait=async(ready,options={})=>naverWaitFor(ready,{guard,sleep:pause,now:()=>Date.now(),...options});
  const requireReady=async(ready,step)=>{
    status.textContent='수집 중 — '+step+' 확인 중…';
    if(!await wait(ready,{settleMs:100,timeoutMs:8000}))throw new Error(step+' 설정을 확인하지 못했습니다 (8초). 해당 필터를 확인하고 다시 시작하세요.');
  };
  const setChecked=async(selector,wanted,step)=>{
    guard();let input=document.querySelector(selector);
    if(!input)throw new Error(step+' 항목을 찾지 못했습니다.');
    if(input.checked===wanted)return;
    const label=document.querySelector(`label[for="${input.id}"]`);
    if(!label)throw new Error(step+' 선택 버튼을 찾지 못했습니다.');
    label.click();
    await requireReady(()=>document.querySelector(selector)?.checked===wanted,step);
  };
  const open=async(label)=>{
    guard();const selector=`.list_filter button[aria-label="${label}"]`,e=document.querySelector(selector);
    if(!e)throw new Error(label+' 필터를 찾지 못했습니다.');
    if(e.getAttribute('aria-pressed')!=='true'){e.click();await requireReady(()=>document.querySelector(selector)?.getAttribute('aria-pressed')==='true',label+' 열기');}
  };
  const shut=async(selector)=>{guard();const e=document.querySelector(selector+' .btn_close_panel');if(e)e.click();await pause(50);};
  start.onclick=async(event)=>{
    event?.stopPropagation();
    if(start.disabled)return;
    complexId=currentId();
    const startedAt=Date.now();
    start.disabled=true;start.textContent='수집 중…';copy.disabled=true;payload=null;preview.textContent='';
    progress.style.display='block';progress.removeAttribute('value');
    status.style.background='#fff0d4';status.textContent='수집 중 — 단지정보 확인 중…';
    try {
      // Finish the initiating click dispatch before opening a site popup.
      // Awaiting open() itself is too late: it clicks before its first yield.
      await pause(0);
      guard();const summary=naverSummary(document);
      status.textContent=`수집 중 — ${summary.name}\n1/3 면적 정보 확인 중…`;
      if(!document.querySelector('#complex_pyeong_tab_list'))throw new Error('먼저 네이버의 단지정보 버튼을 눌러 주세요.');
      await open('면적 선택');
      const unit=async(label)=>{
        guard();const selector=`.filter_popup--type-list button[aria-label="${label}"]`,e=document.querySelector(selector);
        if(!e)throw new Error('면적 단위 버튼 없음');
        if(e.getAttribute('aria-pressed')!=='true')e.click();
        const isPyeong=label==='평으로 평형전환';
        await requireReady(()=>document.querySelector(selector)?.getAttribute('aria-pressed')==='true' &&
          naverOptions(document).length>0 && naverOptions(document).every(t=>isPyeong ? /평$/.test(t.label) : /(?:㎡|m²)$/.test(t.label)),label);
      };
      await unit('제곱미터로 평형전환');const metric=naverOptions(document);
      const exclusive=new Map([...document.querySelectorAll('#complex_pyeong_tab_list [role="tab"]')].map(e=>[naverArea(e.textContent).key,e.title.match(/전용면적\s*([\d.]+)/)?.[1]]));
      await unit('평으로 평형전환');const py=new Map(naverOptions(document).map(e=>[e.value,naverArea(e.label).number]));
      const types=metric.map(t=>({key:naverArea(t.label).key,pyeong:py.get(t.value),exclusive:exclusive.get(naverArea(t.label).key)||''}));
      if(types.some(t=>!Number.isInteger(t.pyeong)))throw new Error('평수 연결을 확인할 수 없습니다.');
      
      await setChecked('#housesize0',true,'전체면적');
      await shut('.filter_popup--type-list');
      status.textContent=`수집 중 — ${summary.name}\n2/3 매매·전세 / 낮은가격순 설정 중…`;
      await open('동 선택');await setChecked('#number0',true,'전체동');await shut('.filter_popup--dong');
      await open('거래방식');
      const trad=()=>[...document.querySelectorAll('.filter_popup--dealtype input')];
      for(const [v,name] of [['A1','매매'],['B1','전세'],['B2','월세'],['B3','단기임대']]){
        const selector=`.filter_popup--dealtype input[value="${v}"]`;
        if(!document.querySelector(selector)&&['B2','B3'].includes(v))continue;
        await setChecked(selector,['A1','B1'].includes(v),name+' 필터');
      }
      await shut('.filter_popup--dealtype');
      if(document.querySelector('#address_group2'))await setChecked('#address_group2',false,'동일매물 묶기 해제');
      const priceSelector='[data-nclk="TAA.price"]';
      const priceState=()=>{const e=document.querySelector(priceSelector);return e?e.getAttribute('aria-pressed')+'|'+e.textContent.trim():'';};
      for(let n=0;n<2;n++){
        if(priceState()==='true|낮은가격순')break;
        const e=document.querySelector(priceSelector);if(!e)throw new Error('가격순 버튼을 찾지 못했습니다.');
        const before=priceState();e.click();
        await requireReady(()=>!!priceState()&&priceState()!==before,'가격 정렬');
      }
      await requireReady(()=>priceState()==='true|낮은가격순','낮은가격순');
      await pause(1000);
      const checkFilters=()=>{
        guard();const e=document.querySelector('[data-nclk="TAA.price"]');
        const active=trad().filter(e=>e.checked).map(e=>e.value).sort().join(',');
        if(active!=='A1,B1'||e?.getAttribute('aria-pressed')!=='true'||e.textContent.trim()!=='낮은가격순'||!document.querySelector('#housesize0')?.checked||!document.querySelector('#number0')?.checked||document.querySelector('#address_group2')?.checked)throw new Error('수집 중 필터가 바뀌었습니다. 다시 시작하세요.');
      };
      checkFilters();
      const expected=naverExpectedCount(document,complexId);
      let listings=[],last=-1,stable=0,complete=false;
      for(let i=0;i<100;i++){
        checkFilters();listings=naverListings(document);
        status.textContent=`수집 중 — ${summary.name}\n3/3 매물 ${listings.length}개 읽음${expected===null?' (전체 개수 확인 중)':' / 전체 '+expected+'개'} · 추가 매물 확인 ${i+1}회`;
        if(expected>0){progress.max=expected;progress.value=Math.min(listings.length,expected);}
        if(expected!==null&&listings.length===expected){complete=true;break;}
        stable=listings.length===last?stable+1:0;last=listings.length;
        if(stable>=5)break;
        const list=document.querySelector('#articleListArea');if(!list)throw new Error('목록을 읽지 못했습니다.');
        let scroller=list;while(scroller&&!(scroller.scrollHeight>scroller.clientHeight+5&&/(auto|scroll)/.test(getComputedStyle(scroller).overflowY)))scroller=scroller.parentElement;
        if(!scroller)break;scroller.scrollTop=scroller.scrollHeight;scroller.dispatchEvent(new Event('scroll',{bubbles:true}));
        // Advance as soon as a new batch has settled instead of always sleeping
        // 1.1s. No-progress attempts still wait the full interval (5 retries).
        const before=listings.length;
        let signature='',changedAt=Date.now();
        await wait(()=>{
          const rows=naverListings(document),next=JSON.stringify(rows);
          if(next!==signature){signature=next;changedAt=Date.now();}
          return rows.length>before && Date.now()-changedAt>=200;
        },{timeoutMs:1100});
      }
      checkFilters();const result=summarizeNaverTypes(types,listings,complete);
      if(!result.types.length)throw new Error('대상 평형이 없습니다.');
      const warnings=[];
      if(!complete)warnings.push((expected===null?'전체 건수 표시를 확인하지 못했습니다.':`전체 ${expected}개 중 ${listings.length}개를 읽었습니다.`)+' 불러온 매물 기준 값이며 미확인 값은 ?입니다.');
      if(result.errors)warnings.push(`${result.errors}개 매물 형식 확인 필요. 최저가를 직접 확인하세요.`);
      payload={source:'https://new.land.naver.com/',complexId,...summary,capturedAt:new Date().toISOString(),complete:complete&&!result.errors,warnings,types:result.types};
      preview.textContent=`${summary.name} ${summary.approvalDate} ${summary.households}세대\n`+result.types.map(g=>`${g.key} / 전용 ${g.exclusiveArea}㎡) ${g.sale}/${g.lease}`).join('\n')+'\n'+warnings.join('\n');
      status.style.background=payload.complete?'#def5df':'#fff0d4';
      status.textContent=`${summary.name} · ${listings.length}개 읽음 · ${((Date.now()-startedAt)/1000).toFixed(1)}초\n`+(payload.complete?'수집 완료 — 가격을 확인하고 결과 복사를 누르세요.':'부분 수집 — 확인 후 복사 가능합니다. 앱에서 검수해야 합니다.');copy.disabled=false;
    }catch(e){status.style.background='#ffe0e0';status.textContent='수집 중단: '+e.message;}finally{start.disabled=false;start.textContent='매매·전세 수집 시작';progress.style.display='none';}
  };
  copy.onclick=async()=>{
    if(!payload)return;
    if(currentId()!==payload.complexId){payload=null;copy.disabled=true;preview.textContent='';status.textContent='단지가 바뀌었습니다. 현재 단지에서 매매·전세 수집 시작을 누르세요.';return;}
    const text='SISEPICKER_NAVER_V1\n'+JSON.stringify(payload);
    try{await navigator.clipboard.writeText(text);status.textContent='복사됨 — 앱의 네이버 부동산 탭에서 붙여넣으세요.';}
    catch(e){const t=document.createElement('textarea');t.value=text;panel.append(t);t.select();if(document.execCommand('copy')){t.remove();status.textContent='복사됨';}else status.textContent='복사가 차단되었습니다. 아래 내용을 Ctrl+C로 복사하세요.';}
  };
})();
