// SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
// SPDX-License-Identifier: MIT
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const money = n => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(Number(n)||0);
  const pct = n => `${Number(n||0).toFixed(2)}%`;
  const set = (id,value) => { $(id).textContent=value; };
  const motionOK = () => typeof window !== 'undefined' &&
    typeof requestAnimationFrame === 'function' &&
    !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const animations = new Map();
  const revealTasks = new Map();
  const revealedCharts = new Set();
  const revealObserver = typeof IntersectionObserver === 'function'
    ? new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (!entry.isIntersecting) return;
          const task = revealTasks.get(entry.target);
          if(task){revealTasks.delete(entry.target);revealObserver.unobserve(entry.target);task();}
        });
      }, {threshold:.18}) : null;
  function whenVisible(element, task) {
    if (!motionOK() || !revealObserver) { task(); return; }
    const box=element.getBoundingClientRect();
    if(box.top < window.innerHeight*.9 && box.bottom > 0) {task();return;}
    revealTasks.set(element, task);revealObserver.observe(element);
  }
  function metric(id, value, format, duration=1150) {
    const element=$(id), target=Number(value);
    if (!Number.isFinite(target)) { set(id,'—'); return; }
    if (!motionOK()) { set(id,format(target)); element.dataset.number=String(target); return; }
    const previous=animations.get(id); if(previous) cancelAnimationFrame(previous);
    const box=element.getBoundingClientRect();
    if(box.bottom<=0 || box.top>=window.innerHeight*.9){
      set(id,format(target));element.dataset.number=String(target);return;
    }
    whenVisible(element, () => {
    const start=Number(element.dataset.number??0), begun=performance.now();
    function frame(now) {
      const progress=Math.min(1,(now-begun)/duration);
      const eased=1-Math.pow(1-progress,3);
      element.textContent=format(start+(target-start)*eased);
      if(progress<1) animations.set(id,requestAnimationFrame(frame));
      else {element.dataset.number=String(target);animations.delete(id);}
    }
    animations.set(id,requestAnimationFrame(frame));
    });
  }

  const profileKey = (profile, stock, count) => {
    const n=Number(count);
    return profile==='aggressive' ? `0/${Number(stock)}/${n}/0`
      : `1/${Number(stock)}/${n}/${profile==='low'?0:Math.min(5,n)}`;
  };
  const chartKey = () => profileKey($('risk-profile').value,$('stock').checked,$('holdings').value);
  const basketKey = () => profileKey($('model-risk-profile').value,$('model-stock').checked,$('model-holdings').value);
  let manifest=null, scenarios=null, activePeriod='120';
  const svgNS='http://www.w3.org/2000/svg';
  const node=(parent,tag,attrs,label)=>{const el=document.createElementNS(svgNS,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,String(v)));if(label!==undefined)el.textContent=label;parent.append(el);return el;};
  function inform(message,error=false){set('scenario-message',message);$('scenario-message').classList.toggle('error',error);}
  function table(target,rows){target.replaceChildren();rows.forEach(cells=>{const tr=document.createElement('tr');cells.forEach(v=>{const td=document.createElement('td');td.textContent=String(v);tr.append(td);});target.append(tr);});}
  const benchmarks = [
    {key:'benchmark',label:'Nifty 50',color:'#82979b'},
    {key:'midcap150',label:'Midcap 150',color:'#ddac68'},
    {key:'smallcap250',label:'Smallcap 250',color:'#a994df'}
  ];
  const benchLevels = key => new Map((manifest?.benchmarks?.monthly||[]).map(row=>[row.date,row[key]]));
  function benchmarkPeriod(months,key,annual=false){
    if(!months.length)return null;
    const all=scenarios?.variants?.[chartKey()]?.months||[];
    const levels=benchLevels(key);
    const first=all.findIndex(row=>row.date===months[0].date);
    const previous=first>0?levels.get(all[first-1].date):manifest?.benchmarks?.initial?.[key];
    const last=levels.get(months.at(-1).date);
    if(!previous||!last)return null;
    const covered=months.every(row=>Number.isFinite(levels.get(row.date)));
    if(!covered)return null;
    const change=last/previous;
    if(annual)return (change-1)*100;
    const years=Math.max((Date.parse(months.at(-1).date)-Date.parse(months[0].date))/86400000/365.25,1/12);
    return (Math.pow(change,1/years)-1)*100;
  }
  const shown=x=>Number.isFinite(x)?pct(x):'—';
  function tables(){
    const research=manifest?.research?.variants?.[chartKey()];
    const all=scenarios?.variants?.[chartKey()]?.months||[];
    const yearly=research?.annual||[];
    const annualRows=yearly.map(x=>{
      const months=all.filter(m=>m.date.startsWith(String(x.year)));
      return [`${x.year}${x.active?' · YTD':''}`,Number(x.return_pct),Number(x.bench_return_pct),
        benchmarkPeriod(months,'midcap150',true),benchmarkPeriod(months,'smallcap250',true)];
    });
    const paint=(id,rows,extra=[])=>{
      const target=$(id);table(target,rows.map(row=>[row[0],...row.slice(1).map(shown)]));
      rows.forEach((row,i)=>{
        const eligible=row.slice(1,5).filter(Number.isFinite);
        if(!eligible.length)return;
        const high=Math.max(...eligible);
        row.slice(1,5).forEach((value,j)=>{if(Number.isFinite(value)&&value===high)target.children[i].children[j+1].classList.add('return-winner');});
      });
    };
    paint('annual-results',annualRows);
    const windows=research?.windows||[],active=research?.active_window;
    const rolling=[...windows,...(active?[active]:[])];
    const format=x=>{
      const months=all.filter(m=>m.date>=x.start&&m.date<=x.end);
      return [x.label||`${x.start} – ${x.end}`,Number(x.cagr_pct),Number(x.bench_cagr_pct),
        benchmarkPeriod(months,'midcap150'),benchmarkPeriod(months,'smallcap250'),Number(x.max_dd_pct)];
    };
    paint('window-results',windows.filter((_,i)=>i%3===0).map(format));
    paint('rolling-results',rolling.map(format));
    set('walkforward-summary',`${windows.length} completed calendar windows${active?` · active trailing window through ${active.end}`:''} · historically selected model`);
    if(!yearly.length)table($('annual-results'),[['Data loading','—','—','—','—']]);
  }
  function renderBasket(){
    if(!manifest)return;
    set('model-holdings-value',`${$('model-holdings').value} stocks`);
    const cached=manifest.holdings?.baskets?.[basketKey()];
    const basket=cached || (basketKey()==='1/1/10/5'?manifest.snapshot?.basket:null);
    const list=$('candidate-positions');list.replaceChildren();
    if(!basket){set('candidate-status','Saved model basket is awaiting the next daily refresh.');return;}
    set('basket-note',!basket.risk_on && $('model-risk-profile').value==='moderate'
      ? 'These are five positions retained from this model’s earlier holdings, ranked by current momentum. Aggressive reselects independently, so its present basket may differ. Target weights are research estimates, not actual investments.'
      : 'Target weights from the research model, not actual investments.');
    set('candidate-status',`Prices through ${basket.date} · ${basket.risk_on?'Invested model':'Retained holdings + cash'} · saved daily`);
    if(!basket.positions.length){set('candidate-status',`Prices through ${basket.date} · 0% equity · 100% cash`);const div=document.createElement('div');div.className='empty-state';div.textContent=basket.risk_on?'No eligible names on this price date.':'No existing holdings retained under this setting; target is cash.';list.append(div);return;}
    const allocated=basket.positions.reduce((sum,p)=>sum+p.weight,0);
    if(!basket.risk_on)set('candidate-status',`Prices through ${basket.date} · ${(allocated*100).toFixed(1)}% retained stocks · ${((1-allocated)*100).toFixed(1)}% cash`);
    basket.positions.forEach(p=>{const row=document.createElement('div');row.className='position';const info=document.createElement('div');const name=document.createElement('strong');name.textContent=p.ticker.replace('.NS','');const note=document.createElement('small');note.textContent='Target allocation';info.append(name,note);const weight=document.createElement('span');weight.className='weight';weight.textContent=`${(p.weight*100).toFixed(1)}%`;row.append(info,weight);list.append(row);});
  }
  function periodRows(months){
    if(activePeriod==='custom')return months.filter(m=>m.date.slice(0,7)>=$('start-month').value && m.date.slice(0,7)<=$('end-month').value);
    return activePeriod==='all'?months:months.slice(-Number(activePeriod));
  }
  function chart(rows,element,tooltipId,forward=false){
    const svg=$(element);svg.replaceChildren();if(!rows.length)return;
    const width=Math.max(260,Math.round(svg.clientWidth)||760);
    const height=Math.max(170,Math.round(svg.clientHeight)||(forward?200:300));
    const left=width<420?58:72,right=width<420?8:18,top=20,bottom=35;
    svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
    const fields=[{key:forward?'model_index':'strategy',label:'Strategy',color:'#67d7ad'},
      ...benchmarks.map(b=>({key:forward?`${b.key}_index`:b.key,label:b.label,color:b.color}))];
    const values=rows.flatMap(r=>fields.map(f=>r[f.key]).filter(Number.isFinite));
    const low=forward?Math.min(...values)*.98:0,high=Math.max(1,...values)*1.07;
    const x=i=>left+(width-left-right)*i/Math.max(1,rows.length-1);
    const y=v=>height-bottom-(v-low)/(high-low||1)*(height-top-bottom);
    for(let i=0;i<=4;i++){
      const value=low+(high-low)*i/4,yy=y(value);
      node(svg,'line',{x1:left,x2:width-right,y1:yy,y2:yy,stroke:'#2d4445','stroke-width':1});
      const label=forward?value.toFixed(0):value>=1e7?`₹${(value/1e7).toFixed(1)}Cr`:value>=1e5?`₹${(value/1e5).toFixed(1)}L`:`₹${(value/1e3).toFixed(0)}k`;
      node(svg,'text',{x:3,y:yy+4,fill:'#a2b6b2','font-size':11},label);
    }
    node(svg,'text',{x:left,y:height-6,fill:'#a2b6b2','font-size':11},rows[0].date.slice(0,7));
    node(svg,'text',{x:width-right,y:height-6,fill:'#a2b6b2','font-size':11,'text-anchor':'end'},rows.at(-1).date.slice(0,7));
    const animate=motionOK()&&!revealedCharts.has(element),paths=[];
    for(const field of fields.slice().reverse()){
      let segment=[];
      function flush(){if(!segment.length)return;const path=node(svg,'path',{d:segment.map(([j,v],n)=>`${n?'L':'M'}${x(j).toFixed(1)},${y(v).toFixed(1)}`).join(' '),fill:'none',stroke:field.color,'stroke-width':field.key==='strategy'||field.key==='model_index'?3:2,'stroke-linecap':'round','stroke-linejoin':'round',pathLength:1,class:animate?'path-pending':''});paths.push(path);segment=[];}
      rows.forEach((row,j)=>{if(Number.isFinite(row[field.key]))segment.push([j,row[field.key]]);else flush();});flush();
    }
    if(animate)whenVisible(svg,()=>{revealedCharts.add(element);paths.forEach((path,i)=>{path.classList.remove('path-pending');path.classList.add('draw-path');path.style.animationDelay=`${i*80}ms`;});});
    const cross=node(svg,'line',{x1:0,x2:0,y1:top,y2:height-bottom,stroke:'#d1e7dd','stroke-width':1,'stroke-dasharray':'4 4',visibility:'hidden'});
    const hit=node(svg,'rect',{x:left,y:top,width:width-left-right,height:height-top-bottom,fill:'transparent',tabindex:0,'aria-label':'Move pointer or use arrow keys to inspect dates'});
    const tip=tooltipId?$(tooltipId):null;
    function inspect(i){i=Math.max(0,Math.min(rows.length-1,i));const p=rows[i];cross.setAttribute('x1',x(i));cross.setAttribute('x2',x(i));cross.setAttribute('visibility','visible');
      if(tip){const base=p.contributed||rows[0].strategy;const entries=fields.filter(f=>Number.isFinite(p[f.key])).map(f=>{const value=p[f.key],change=base?(value/base-1)*100:0;return `${f.label} ${money(value)} (${change>=0?'+':''}${pct(change)})`;});tip.hidden=false;tip.textContent=`${p.date} · ${entries.join(' · ')} · return vs contributed`;tip.style.left=`${Math.max(8,Math.min(75,100*x(i)/width-15))}%`;}
    }
    hit.addEventListener('pointermove',e=>{const rect=svg.getBoundingClientRect();const local=(e.clientX-rect.left)/rect.width*width;inspect(Math.round((local-left)/(width-left-right)*(rows.length-1)));});
    hit.addEventListener('pointerleave',()=>{cross.setAttribute('visibility','hidden');if(tip)tip.hidden=true;});
    let focusIndex=rows.length-1;hit.addEventListener('focus',()=>inspect(focusIndex));hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();inspect(focusIndex+=e.key==='ArrowRight'?1:-1);focusIndex=Math.max(0,Math.min(rows.length-1,focusIndex));}});
    svg.setAttribute('aria-label',`Strategy, Nifty 50, Midcap 150 and Smallcap 250 from ${rows[0].date} through ${rows.at(-1).date}`);
  }
  function renderBacktest(){
    set('lump-value',money($('lump').value));set('sip-value',money($('sip').value));set('holdings-value',`${$('holdings').value} stocks`);
    if(!manifest)return;
    const variant=scenarios?.variants?.[chartKey()];
    if(!variant){set('chart-mode','Loading cached history');inform('Loading the saved research paths…');return;}
    const k=variant.kpis;
    metric('kpi-cagr',k.cagr_pct,pct);metric('kpi-drawdown',k.max_drawdown_pct,pct);metric('kpi-sharpe',k.sharpe,n=>n.toFixed(2));metric('kpi-benchmark',k.benchmark_cagr_pct,pct);
    set('kpi-source',`Saved ${$('holdings').value}-stock backtest · ${k.start}–${k.end}`);
    set('chart-mode',`Saved path · ${$('holdings').value} holdings`);
    set('chart-detail',`Monthly checkpoints · through ${scenarios.data_through}`);
    const months=periodRows(variant.months);
    if(!months.length){$('growth-chart').replaceChildren();inform('Select a valid range inside the saved period.',true);return;}
    let a=Number($('lump').value),b=a,paid=a;const sip=Number($('sip').value);
    const extra={};for(const key of ['midcap150','smallcap250']){const levels=benchLevels(key),all=variant.months,first=all.findIndex(m=>m.date===months[0].date),prior=first>0?levels.get(all[first-1].date):manifest?.benchmarks?.initial?.[key];extra[key]={levels,previous:prior,value:prior?Number($('lump').value):null};}
    // Month-end checkpoints represent each period's actual saved return; the
    // deposit is applied before each corresponding month's return.
    const points=[{date:`${months[0].date.slice(0,7)}-01`,strategy:a,benchmark:b,midcap150:extra.midcap150.value,smallcap250:extra.smallcap250.value,contributed:paid}];
    months.forEach(m=>{a=(a+sip)*(1+m.strategy_return);b=(b+sip)*(1+m.benchmark_return);paid+=sip;const point={date:m.date,strategy:a,benchmark:b,contributed:paid};for(const key of Object.keys(extra)){const item=extra[key],level=item.levels.get(m.date);if(item.previous&&level&&item.value!==null)item.value=(item.value+sip)*level/item.previous;else item.value=null;point[key]=item.value;item.previous=level;}points.push(point);});
    metric('strategy-total',a,money);metric('benchmark-total',b,money);for(const key of ['midcap150','smallcap250']){if(extra[key].value===null)set(`${key.replace('150','').replace('250','')}-total`,'—');else metric(`${key.replace('150','').replace('250','')}-total`,extra[key].value,money);}metric('contributed-total',paid,money);
    set('chart-period',`${months[0].date.slice(0,7)} — ${months.at(-1).date.slice(0,7)}`);
    chart(points,'growth-chart','growth-tooltip');
    inform(`Saved ${$('holdings').value}-stock path through ${scenarios.data_through}. Investment values are illustrative.`);
    tables();
  }
  function forward(){
    if(!manifest)return;
    const recorded=manifest.snapshot?.forward||[];
    const history=scenarios?.variants?.['1/1/10/5']?.months?.filter(m=>m.date.slice(0,4)==='2026')||[];
    let a=100,b=100;const extra={};for(const key of ['midcap150','smallcap250']){const levels=benchLevels(key),all=scenarios?.variants?.['1/1/10/5']?.months||[],first=all.findIndex(m=>m.date===history[0]?.date),prior=first>0?levels.get(all[first-1].date):manifest?.benchmarks?.initial?.[key];extra[key]={levels,previous:prior,value:prior?100:null};}
    const reconstructed=history.length?[{date:'2026-01-01',model_index:100,benchmark_index:100,midcap150_index:extra.midcap150.value,smallcap250_index:extra.smallcap250.value},...history.map(m=>{a*=1+m.strategy_return;b*=1+m.benchmark_return;const point={date:m.date,model_index:a,benchmark_index:b};for(const key of Object.keys(extra)){const item=extra[key],level=item.levels.get(m.date);if(item.previous&&level&&item.value!==null)item.value*=level/item.previous;else item.value=null;point[`${key}_index`]=item.value;item.previous=level;}return point;})]:[];
    // Never splice distinct retrospectively calculated and daily observed series.
    const use=reconstructed.length?reconstructed:recorded;
    if(use.length){metric('forward-model',use.at(-1).model_index,n=>n.toFixed(2));metric('forward-nifty',use.at(-1).benchmark_index,n=>n.toFixed(2));for(const key of ['midcap150','smallcap250']){const value=use.at(-1)[`${key}_index`];if(Number.isFinite(value))metric(`forward-${key.replace('150','').replace('250','')}`,value,n=>n.toFixed(2));else set(`forward-${key.replace('150','').replace('250','')}`,'—');}}
    set('forward-period',use.length?`${use[0].date} — ${use.at(-1).date}`:'Awaiting saved path');
    chart(use,'forward-chart',null,true);
    $('forward-chart').setAttribute('aria-label',reconstructed.length?'Retrospective 2026 backtest path from January':'Recorded daily model from first public snapshot');
  }
  document.querySelectorAll('[data-risk-control]').forEach(control=>{
    const input=$(control.dataset.riskControl);
    control.querySelectorAll('[data-risk]').forEach(button=>button.addEventListener('click',()=>{
      input.value=button.dataset.risk;
      control.dataset.active=button.dataset.risk;
      control.querySelectorAll('[data-risk]').forEach(choice=>choice.setAttribute('aria-pressed',String(choice===button)));
      if(input.id==='risk-profile'){revealedCharts.delete('growth-chart');renderBacktest();}
      else renderBasket();
    }));
  });
  ['lump','sip','stock','holdings'].forEach(id=>{
    $(id).addEventListener('input',renderBacktest);
    $(id).addEventListener('change',()=>{revealedCharts.delete('growth-chart');renderBacktest();});
  });
  ['model-stock','model-holdings'].forEach(id=>$(id).addEventListener('input',renderBasket));
  document.querySelectorAll('[data-period]').forEach(button=>button.addEventListener('click',()=>{activePeriod=button.dataset.period;revealedCharts.delete('growth-chart');document.querySelectorAll('[data-period]').forEach(b=>b.classList.toggle('active',b===button));renderBacktest();}));
  ['start-month','end-month'].forEach(id=>$(id).addEventListener('input',()=>{activePeriod='custom';revealedCharts.delete('growth-chart');document.querySelectorAll('[data-period]').forEach(b=>b.classList.remove('active'));renderBacktest();}));
  async function staticJson(name) {
    const upstream=`https://raw.githubusercontent.com/Juiceyyyy/AlphEdge/main/state/${name}`;
    try {const response=await fetch(upstream,{cache:'no-store'});if(response.ok)return await response.json();}
    catch (_) { /* use the deployed copy below */ }
    const local=await fetch(`/data/${name}`);
    if(!local.ok)throw Error(`${name} unavailable`);
    return local.json();
  }
  async function load(){
    try{
      if(window.ALPHEDGE_STATIC){
        const [snapshot,research,holdings,paths,benchmarkData]=await Promise.all([
          staticJson('current_snapshot.json'),staticJson('research_cache.json'),
          staticJson('holdings_cache.json'),staticJson('scenarios.json'),staticJson('benchmarks.json').catch(()=>null)]);
        manifest={snapshot,research,holdings,benchmarks:benchmarkData?.strategy_id===paths.strategy_id?benchmarkData:null};
        scenarios=paths;
      }else{
        const [overview,paths]=await Promise.all([fetch('/api/explore',{cache:'no-store'}),fetch('/api/explore/scenarios')]);
        if(!overview.ok||!paths.ok)throw Error('Saved data could not be fetched');
        manifest=await overview.json();scenarios=await paths.json();
        if(!manifest.benchmarks){try{manifest.benchmarks=await staticJson('benchmarks.json');}catch(_){manifest.benchmarks=null;}}
      }
      if(manifest.benchmarks?.data_through!==scenarios?.data_through)manifest.benchmarks=null;
      if(scenarios?.strategy_id!=='hold-five-v1'||manifest?.research?.strategy_id!=='hold-five-v1'||manifest?.holdings?.strategy_id!=='hold-five-v1'||manifest?.snapshot?.strategy_id!=='hold-five-v1'||!scenarios?.variants?.['1/1/10/5'])throw Error('Updated research is being calculated. The page checks for verified results automatically.');
      const months=scenarios.variants['1/1/10/5'].months;
      $('start-month').min=months[0].date.slice(0,7);$('start-month').max=months.at(-1).date.slice(0,7);
      $('end-month').min=months[0].date.slice(0,7);$('end-month').max=months.at(-1).date.slice(0,7);
      if(!$('start-month').value)$('start-month').value=months[0].date.slice(0,7);
      if(!$('end-month').value)$('end-month').value=months.at(-1).date.slice(0,7);
      renderBacktest();renderBasket();forward();
    }catch(e){manifest=null;scenarios=null;inform(e.message.startsWith('Updated research')?e.message:`Saved research is temporarily unavailable (${e.message}). The page will retry automatically.`,true);set('chart-mode','Awaiting verified data');set('candidate-status','Updating the model basket. This page retries automatically.');}
  }
  if(typeof window.addEventListener==='function'){
    let resizeTimer;
    window.addEventListener('resize',()=>{
      clearTimeout(resizeTimer);
      resizeTimer=setTimeout(()=>{if(manifest&&scenarios){renderBacktest();forward();}},120);
    });
  }
  load();setInterval(load,60*1000);
})();
