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

  const key = (a,b,c) => `${Number(a)}/${Number(b)}/${Number(c)}`;
  const chartKey = () => key($('trend').checked,$('stock').checked,$('holdings').value);
  const basketKey = () => key($('model-trend').checked,$('model-stock').checked,$('model-holdings').value);
  let manifest=null, scenarios=null, activePeriod='120';
  const svgNS='http://www.w3.org/2000/svg';
  const node=(parent,tag,attrs,label)=>{const el=document.createElementNS(svgNS,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,String(v)));if(label!==undefined)el.textContent=label;parent.append(el);return el;};
  function inform(message,error=false){set('scenario-message',message);$('scenario-message').classList.toggle('error',error);}
  function table(target,rows){target.replaceChildren();rows.forEach(cells=>{const tr=document.createElement('tr');cells.forEach(v=>{const td=document.createElement('td');td.textContent=String(v);tr.append(td);});target.append(tr);});}
  function tables(){
    const research=manifest?.research?.variants?.[chartKey()];
    const yearly=research?.annual || manifest?.backtest?.yearly || [];
    table($('annual-results'),yearly.map(x=>[`${x.year}${x.active?' · YTD':''}`,pct(x.return_pct),pct(x.bench_return_pct)]));
    const windows=research?.windows || manifest?.windows || [];
    const active=research?.active_window;
    const rolling=research ? [...windows, ...(active?[active]:[])] : manifest?.rolling_windows || [];
    const format=x=>[x.label || `${x.start} – ${x.end}`,pct(x.cagr_pct),pct(x.bench_cagr_pct),pct(x.max_dd_pct)];
    table($('window-results'),windows.filter((_,i)=>i%3===0).map(format));
    table($('rolling-results'),rolling.map(format));
    set('walkforward-summary',`${windows.length} completed calendar windows${active ? ` · active trailing window through ${active.end}`:''} · historically selected model`);
    if(!yearly.length)table($('annual-results'),[['Data loading','—','—']]);
  }
  function renderBasket(){
    if(!manifest)return;
    set('model-holdings-value',`${$('model-holdings').value} stocks`);
    const cached=manifest.holdings?.baskets?.[basketKey()];
    const basket=cached || (basketKey()==='1/1/10'?manifest.snapshot?.basket:null);
    const list=$('candidate-positions');list.replaceChildren();
    if(!basket){set('candidate-status','Saved model basket is awaiting the next daily refresh.');return;}
    set('candidate-status',`Prices through ${basket.date} · ${basket.risk_on?'Invested model':'Cash allocation'} · saved daily`);
    if(!basket.positions.length){const div=document.createElement('div');div.className='empty-state';div.textContent=basket.risk_on?'No eligible names on this price date.':'Nifty trend filter indicates 100% cash.';list.append(div);return;}
    basket.positions.forEach(p=>{const row=document.createElement('div');row.className='position';const info=document.createElement('div');const name=document.createElement('strong');name.textContent=p.ticker.replace('.NS','');const note=document.createElement('small');note.textContent='Target allocation';info.append(name,note);const weight=document.createElement('span');weight.className='weight';weight.textContent=`${(p.weight*100).toFixed(1)}%`;row.append(info,weight);list.append(row);});
  }
  function periodRows(months){
    if(activePeriod==='custom')return months.filter(m=>m.date.slice(0,7)>=$('start-month').value && m.date.slice(0,7)<=$('end-month').value);
    return activePeriod==='all'?months:months.slice(-Number(activePeriod));
  }
  function chart(rows,element,tooltipId,forward=false){
    const svg=$(element);svg.replaceChildren();if(!rows.length)return;
    const width=760,height=forward?200:300,left=72,right=18,top=20,bottom=35;
    const fields=forward?['model_index','benchmark_index']:['strategy','benchmark'];
    const values=rows.flatMap(r=>fields.map(k=>r[k]));
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
    const animate=motionOK() && !revealedCharts.has(element);
    const paths=fields.slice().reverse().map((field,i)=>node(svg,'path',{d:rows.map((r,j)=>`${j?'L':'M'}${x(j).toFixed(1)},${y(r[field]).toFixed(1)}`).join(' '),fill:'none',stroke:i?'#67d7ad':'#82979b','stroke-width':i?3:2,'stroke-linecap':'round','stroke-linejoin':'round',pathLength:1,class:animate?'path-pending':''}));
    if(animate) whenVisible(svg,()=>{
      revealedCharts.add(element);
      paths.forEach((path,i)=>{path.classList.remove('path-pending');path.classList.add('draw-path');path.style.animationDelay=`${i*120}ms`;});
    });
    const cross=node(svg,'line',{x1:0,x2:0,y1:top,y2:height-bottom,stroke:'#d1e7dd','stroke-width':1,'stroke-dasharray':'4 4',visibility:'hidden'});
    const hit=node(svg,'rect',{x:left,y:top,width:width-left-right,height:height-top-bottom,fill:'transparent',tabindex:0,'aria-label':'Move pointer or use arrow keys to inspect dates'});
    const tip=tooltipId?$(tooltipId):null;
    function inspect(i){i=Math.max(0,Math.min(rows.length-1,i));const p=rows[i];cross.setAttribute('x1',x(i));cross.setAttribute('x2',x(i));cross.setAttribute('visibility','visible');
      if(tip){const a=p[fields[0]],b=p[fields[1]],base=rows[0];const contributed=p.contributed||base[fields[0]];const ar=contributed?((a/contributed-1)*100):0,br=contributed?((b/contributed-1)*100):0;tip.hidden=false;tip.textContent=`${p.date}  ·  Strategy ${money(a)} (${ar>=0?'+':''}${pct(ar)})  ·  Nifty ${money(b)} (${br>=0?'+':''}${pct(br)})  ·  return vs contributed`;tip.style.left=`${Math.max(8,Math.min(75,100*x(i)/width-15))}%`;}
    }
    hit.addEventListener('pointermove',e=>{const rect=svg.getBoundingClientRect();const local=(e.clientX-rect.left)/rect.width*width;inspect(Math.round((local-left)/(width-left-right)*(rows.length-1)));});
    hit.addEventListener('pointerleave',()=>{cross.setAttribute('visibility','hidden');if(tip)tip.hidden=true;});
    let focusIndex=rows.length-1;hit.addEventListener('focus',()=>inspect(focusIndex));hit.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();inspect(focusIndex+=e.key==='ArrowRight'?1:-1);focusIndex=Math.max(0,Math.min(rows.length-1,focusIndex));}});
    svg.setAttribute('aria-label',`Strategy and Nifty from ${rows[0].date} through ${rows.at(-1).date}`);
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
    // Month-end checkpoints represent each period's actual saved return; the
    // deposit is applied before each corresponding month's return.
    const points=[{date:`${months[0].date.slice(0,7)}-01`,strategy:a,benchmark:b,contributed:paid}];
    months.forEach(m=>{a=(a+sip)*(1+m.strategy_return);b=(b+sip)*(1+m.benchmark_return);paid+=sip;points.push({date:m.date,strategy:a,benchmark:b,contributed:paid});});
    metric('strategy-total',a,money);metric('benchmark-total',b,money);metric('contributed-total',paid,money);
    set('chart-period',`${months[0].date.slice(0,7)} — ${months.at(-1).date.slice(0,7)}`);
    chart(points,'growth-chart','growth-tooltip');
    inform(`Saved ${$('holdings').value}-stock path through ${scenarios.data_through}. Investment values are illustrative.`);
    tables();
  }
  function forward(){
    if(!manifest)return;
    const recorded=manifest.snapshot?.forward||[];
    const history=scenarios?.variants?.['1/1/10']?.months?.filter(m=>m.date.slice(0,4)==='2026')||[];
    let a=100,b=100;
    const reconstructed=history.length?[{date:'2026-01-01',model_index:100,benchmark_index:100},...history.map(m=>{a*=1+m.strategy_return;b*=1+m.benchmark_return;return{date:m.date,model_index:a,benchmark_index:b};})]:[];
    // Never splice distinct retrospectively calculated and daily observed series.
    const use=reconstructed.length?reconstructed:recorded;
    if(use.length){metric('forward-model',use.at(-1).model_index,n=>n.toFixed(2));metric('forward-nifty',use.at(-1).benchmark_index,n=>n.toFixed(2));}
    set('forward-period',use.length?`${use[0].date} — ${use.at(-1).date}`:'Awaiting saved path');
    chart(use,'forward-chart',null,true);
    $('forward-chart').setAttribute('aria-label',reconstructed.length?'Retrospective 2026 backtest path from January':'Recorded daily model from first public snapshot');
  }
  ['lump','sip','trend','stock','holdings'].forEach(id=>{
    $(id).addEventListener('input',renderBacktest);
    $(id).addEventListener('change',()=>{revealedCharts.delete('growth-chart');renderBacktest();});
  });
  ['model-trend','model-stock','model-holdings'].forEach(id=>$(id).addEventListener('input',renderBasket));
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
        const [snapshot,research,holdings,paths,baseline,wf]=await Promise.all([
          staticJson('current_snapshot.json'),staticJson('research_cache.json'),
          staticJson('holdings_cache.json'),staticJson('scenarios.json'),
          staticJson('winner_max_sharpe.json'),staticJson('walk_forward.json')]);
        manifest={snapshot,research,holdings,backtest:baseline,
          windows:wf.windows_3y||[],rolling_windows:wf.rolling_3y_step_6m||[]};
        scenarios=paths;
      }else{
        const [overview,paths]=await Promise.all([fetch('/api/explore',{cache:'no-store'}),fetch('/api/explore/scenarios')]);
        if(!overview.ok||!paths.ok)throw Error('Saved data could not be fetched');
        manifest=await overview.json();scenarios=await paths.json();
      }
      if(!scenarios?.variants?.['1/1/10'])throw Error('The historical cache is temporarily unavailable');
      const months=scenarios.variants['1/1/10'].months;
      $('start-month').min=months[0].date.slice(0,7);$('start-month').max=months.at(-1).date.slice(0,7);
      $('end-month').min=months[0].date.slice(0,7);$('end-month').max=months.at(-1).date.slice(0,7);
      if(!$('start-month').value)$('start-month').value=months[0].date.slice(0,7);
      if(!$('end-month').value)$('end-month').value=months.at(-1).date.slice(0,7);
      renderBacktest();renderBasket();forward();
    }catch(e){inform(`Saved research could not load: ${e.message}. Please reload the page.`,true);set('candidate-status','Daily basket unavailable.');}
  }
  load();setInterval(load,15*60*1000);
})();
