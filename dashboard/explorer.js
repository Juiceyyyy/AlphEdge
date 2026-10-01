(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const money = n => new Intl.NumberFormat("en-IN", {
    style:"currency", currency:"INR", maximumFractionDigits:0
  }).format(Number(n) || 0);
  const pct = n => (Number(n) || 0).toFixed(2) + "%";
  let overview, datesInitialized = false;

  const settings = () => ({
    trend_filter: $("trend").checked,
    stock_filter: $("stock").checked,
    n_hold: Number($("holdings").value)
  });
  const settingsKey = s => [Number(s.trend_filter), Number(s.stock_filter), s.n_hold].join("/");
  const amount = id => {
    const value=Number($(id+"-input").value);
    return Number.isFinite(value) ? Math.min(Math.max(0,value),1e10) : 0;
  };
  const message = (text, error=false) => {
    $("scenario-message").textContent = text;
    $("scenario-message").classList.toggle("error", error);
  };
  const setText = (id, value) => { $(id).textContent = value; };

  function baselineMonths() {
    // The stored backtest only has annual checkpoints. Monthly interpolation is
    // deliberately labelled as an illustration, never as the actual price path.
    const rows = overview.backtest.yearly.filter(x => x.year > 2011 && x.year < 2026);
    return rows.flatMap(row => {
      const r = Math.max(-.9999, Number(row.return_pct)/100);
      const b = Math.max(-.9999, Number(row.bench_return_pct)/100);
      const monthly = Math.pow(1+r, 1/12)-1;
      const benchmark = Math.pow(1+b, 1/12)-1;
      return Array.from({length:12}, (_, i) => ({
        date: `${row.year}-${String(i+1).padStart(2,"0")}-28`,
        strategy_return:monthly, benchmark_return:benchmark
      }));
    });
  }

  function replay(months) {
    const first = $("start-month").value, last = $("end-month").value;
    const chosen = months.filter(m => m.date.slice(0,7) >= first && m.date.slice(0,7) <= last);
    if (!chosen.length) {
      ["strategy-total","benchmark-total","contributed-total","chart-period"].forEach(id=>setText(id,"—"));
      $("growth-chart").replaceChildren();
      message("Select a period within the saved historical data, with From before Through.", true);
      return;
    }
    let strategy = amount("lump");
    let benchmark = strategy;
    let contributed = strategy;
    const sip = amount("sip");
    const points = [{date:chosen[0]?.date || "", strategy, benchmark}];
    chosen.forEach((m, i) => {
      strategy = (strategy + sip) * (1 + Number(m.strategy_return || 0));
      benchmark = (benchmark + sip) * (1 + Number(m.benchmark_return || 0));
      contributed += sip;
      if (i % 3 === 2 || i === chosen.length - 1)
        points.push({date:m.date, strategy, benchmark});
    });
    setText("strategy-total", money(strategy));
    setText("benchmark-total", money(benchmark));
    setText("contributed-total", money(contributed));
    setText("chart-period", chosen.length ?
      `${chosen[0].date.slice(0,7)} — ${chosen.at(-1).date.slice(0,7)}` : "—");
    draw(points);
  }

  function draw(points) {
    const svg = $("growth-chart");
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (!points.length) return;
    const NS = "http://www.w3.org/2000/svg", width = 760, height = 300;
    const left = 66, right = 16, top = 16, bottom = 34;
    const max = Math.max(1, ...points.map(p => Math.max(p.strategy,p.benchmark))) * 1.08;
    const x = i => left + (width-left-right)*i/Math.max(points.length-1,1);
    const y = v => height-bottom - Math.max(0,v)/max*(height-top-bottom);
    function node(tag, attrs, content) {
      const e = document.createElementNS(NS,tag);
      for (const [k,v] of Object.entries(attrs)) e.setAttribute(k,String(v));
      if (content !== undefined) e.textContent = content;
      svg.appendChild(e); return e;
    }
    for (let i=0;i<=4;i++) {
      const val = max*i/4, yy = y(val);
      node("line",{x1:left,x2:width-right,y1:yy,y2:yy,stroke:"#263638","stroke-width":1});
      node("text",{x:3,y:yy+4,fill:"#8ba5a3","font-size":11},val>=10000000 ?
        "₹"+(val/10000000).toFixed(1)+"Cr" : val>=100000 ?
        "₹"+(val/100000).toFixed(1)+"L" : "₹"+Math.round(val/1000)+"k");
    }
    const first = points[0].date, last = points.at(-1).date;
    node("text",{x:left,y:height-7,fill:"#8ba5a3","font-size":11},first.slice(0,7));
    node("text",{x:width-right,y:height-7,fill:"#8ba5a3","font-size":11,"text-anchor":"end"},last.slice(0,7));
    for (const [key,color] of [["benchmark","#789095"],["strategy","#67d7ad"]]) {
      const d = points.map((p,i)=>`${i?"L":"M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
      node("path",{d,fill:"none",stroke:color,"stroke-width":key==="strategy"?3:2,
                   "stroke-linecap":"round","stroke-linejoin":"round"});
    }
    svg.setAttribute("aria-label",
      `Investment illustration from ${first.slice(0,7)} to ${last.slice(0,7)}. Strategy ${money(points.at(-1).strategy)}; Nifty ${money(points.at(-1).benchmark)}.`);
  }

  function updateIllustration() {
    setText("lump-value",money(amount("lump")));
    setText("sip-value",money(amount("sip")));
    setText("holdings-value",$("holdings").value+" stocks");
    if (!overview) return;
    const key = settingsKey(settings());
    const variant = overview.scenarios?.variants?.[key];
    if (!datesInitialized) {
      const source = variant?.months?.length ? variant.months : baselineMonths();
      if (source.length) {
        const last = source.at(-1).date.slice(0,7);
        const first = source[0].date.slice(0,7);
        const [year, month] = last.split("-");
        $("start-month").min = first; $("end-month").min = first;
        $("start-month").max = last; $("end-month").max = last;
        $("start-month").value = `${Math.max(Number(year)-10,Number(first.slice(0,4)))}-${month}`;
        $("end-month").value = last;
        datesInitialized = true;
      }
    }
    if (variant?.months?.length) {
      const k=variant.kpis;
      setText("kpi-cagr",pct(k.cagr_pct));setText("kpi-drawdown",pct(k.max_drawdown_pct));
      setText("kpi-sharpe",Number(k.sharpe||0).toFixed(2));
      setText("kpi-benchmark",pct(k.benchmark_cagr_pct));
      setText("kpi-source",`Saved ${$("holdings").value}-stock scenario · ${k.start}–${k.end}`);
      setText("chart-mode", "Saved scenario · " + key.replaceAll("/", " · "));
      setText("chart-detail", `Monthly backtest checkpoints · generated ${overview.scenarios.computed_at.slice(0,10)}`);
      replay(variant.months);
      message(`Showing the saved ${$("holdings").value}-stock historical run. Rules and investment inputs update the chart instantly. Historical CAGR ${pct(variant.kpis.cagr_pct)}; maximum drawdown ${pct(variant.kpis.max_drawdown_pct)}.`);
    } else if (key === "1/1/10") {
      const k=overview.backtest.kpis;
      setText("kpi-cagr",pct(k.cagr_pct));setText("kpi-drawdown",pct(k.max_drawdown_pct));
      setText("kpi-sharpe",Number(k.sharpe||0).toFixed(2));
      setText("kpi-benchmark",pct(k.benchmark_cagr_pct));
      setText("kpi-source",`Saved baseline · ${k.start || "2011"}–${k.end || "2026"}`);
      setText("chart-mode", "Saved annual baseline");
      setText("chart-detail", "Illustrative monthly values from annual results");
      replay(baselineMonths());
      message("The monthly scenario cache is pending. This default chart spreads annual returns evenly over each year; it is an illustration.");
    } else {
      setText("chart-mode", "Scenario cache pending");
      message("This historical scenario is not available yet. The weekly cache build is pending; return to the default filters and 10 stocks for the saved baseline.", true);
      $("growth-chart").replaceChildren();
      ["strategy-total","benchmark-total","contributed-total","chart-period"].forEach(id=>setText(id,"—"));
    }
  }

  function setPending() {
    if(settingsKey(settings()) !== "1/1/10")
      setText("candidate-status","Showing the daily baseline basket. Select Refresh holdings to calculate the chosen rules.");
    else if(overview?.snapshot)
      setText("candidate-status",`Daily baseline · prices through ${overview.snapshot.price_date}`);
  }

  function renderForward(rows) {
    const svg=$("forward-chart");svg.replaceChildren();
    setText("forward-period",rows.length ? `${rows[0].date} — ${rows.at(-1).date}` : "Awaiting first refresh");
    setText("forward-model",rows.length ? rows.at(-1).model_index.toFixed(2) : "—");
    setText("forward-nifty",rows.length ? rows.at(-1).benchmark_index.toFixed(2) : "—");
    if(!rows.length) return;
    const NS="http://www.w3.org/2000/svg", width=760, height=200;
    const values=rows.flatMap(r=>[r.model_index,r.benchmark_index]);
    const min=Math.min(...values)*.98, max=Math.max(...values)*1.02;
    const x=i=>36+(width-52)*i/Math.max(rows.length-1,1);
    const y=value=>height-22-(value-min)/(max-min||1)*(height-42);
    for(const [key,color] of [["benchmark_index","#789095"],["model_index","#67d7ad"]]) {
      const path=document.createElementNS(NS,"path");
      path.setAttribute("d",rows.map((r,i)=>`${i?"L":"M"}${x(i).toFixed(1)},${y(r[key]).toFixed(1)}`).join(" "));
      path.setAttribute("fill","none");path.setAttribute("stroke",color);
      path.setAttribute("stroke-width",key==="model_index"?3:2);
      path.setAttribute("stroke-linecap","round");svg.appendChild(path);
    }
    svg.setAttribute("aria-label",`Forward research model index ${rows.at(-1).model_index.toFixed(2)} and Nifty index ${rows.at(-1).benchmark_index.toFixed(2)} through ${rows.at(-1).date}. Both began at 100 on ${rows[0].date}.`);
  }

  function renderResearchTables(data) {
    const annual = $("annual-results"), windows = $("window-results"), rolling = $("rolling-results");
    const row = (target, cells) => {
      const tr = document.createElement("tr");
      cells.forEach(value => { const td = document.createElement("td"); td.textContent = value; tr.append(td); });
      target.append(tr);
    };
    annual.replaceChildren(); windows.replaceChildren(); rolling.replaceChildren();
    (data.backtest.yearly || []).forEach(x => row(annual,
      [x.year, pct(x.return_pct), pct(x.bench_return_pct)]));
    (data.windows || []).forEach(x => row(windows,
      [x.label || `${x.start} – ${x.end}`, pct(x.cagr_pct), pct(x.bench_cagr_pct), pct(x.max_dd_pct)]));
    (data.rolling_windows || []).forEach(x => row(rolling,
      [`${x.start} – ${x.end}`, pct(x.cagr_pct), pct(x.bench_cagr_pct), pct(x.max_dd_pct)]));
    const periods = data.windows || [];
    const beats = periods.filter(x => x.cagr_pct > x.bench_cagr_pct).length;
    setText("walkforward-summary", `${beats} of ${periods.length} consecutive periods exceeded Nifty 50 · ${rolling.childElementCount} overlapping windows available`);
    if (!annual.childElementCount) row(annual, ["No saved results", "—", "—"]);
    if (!windows.childElementCount) row(windows, ["No saved windows", "—", "—", "—"]);
    if (!rolling.childElementCount) row(rolling, ["No saved rolling windows", "—", "—", "—"]);
  }

  function position(list,ticker,weight,caption) {
    const row=document.createElement("div");row.className="position";
    const left=document.createElement("div");
    const name=document.createElement("strong");name.textContent=ticker.replace(".NS","");
    const note=document.createElement("small");note.textContent=caption;
    left.append(name,note);
    const right=document.createElement("span");right.className="weight";
    right.textContent=(100*weight).toFixed(1)+"%";
    row.append(left,right);list.append(row);
  }

  async function post(url, body) {
    const controller = new AbortController();
    const timer = setTimeout(()=>controller.abort(),180000);
    try {
      const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify(body),signal:controller.signal});
      const data=await response.json();
      if(!response.ok) throw new Error(data.detail || "The calculation was unavailable.");
      return data;
    } finally { clearTimeout(timer); }
  }

  async function calculateCandidates() {
    const button=$("calculate-candidates"), chosen=settings();
    button.disabled=true; button.textContent="Calculating candidates…";
    setText("candidate-status","Downloading latest available prices and applying the rules…");
    try {
      const data=await post("/api/explore/candidates",chosen);
      const list=$("candidate-positions");list.replaceChildren();
      setText("candidate-status",
        `Prices through ${data.date} · ${data.risk_on?"Invested model":"Cash allocation"} · Calculated ${new Date(data.computed_at).toLocaleString("en-IN")}`);
      if(data.positions.length) data.positions.forEach(p =>
        position(list,p.ticker,p.weight,"Model target weight"));
      else {
        const div=document.createElement("div");div.className="empty-state";
        div.textContent=data.risk_on?"No eligible candidates with current data.":"Nifty trend filter indicates a 100% cash allocation.";
        list.append(div);
      }
      if(settingsKey(settings())!==settingsKey(chosen)) setPending();
    } catch(e) {
      setText("candidate-status",
        `Model holdings unavailable: ${e.name==="AbortError"?"request timed out":e.message}. Try refreshing later.`);
    } finally {button.disabled=false;button.innerHTML='Calculate current candidates <span aria-hidden="true">→</span>';}
  }

  ["lump","sip"].forEach(id=>{
    $(id).addEventListener("input",()=>{$(id+"-input").value=$(id).value;updateIllustration();});
    $(id+"-input").addEventListener("input",()=>{
      $(id).value=Math.min(amount(id),Number($(id).max));updateIllustration();
    });
  });
  ["start-month","end-month"].forEach(id=>$(id).addEventListener("input",updateIllustration));
  ["trend","stock","holdings"].forEach(id=>$(id).addEventListener("input",()=>{
    updateIllustration();setPending();
  }));
  $("calculate-candidates").addEventListener("click",calculateCandidates);
  updateIllustration();
  function loadOverview() {
    return fetch("/api/explore").then(r=>{if(!r.ok)throw Error("Data unavailable");return r.json();})
    .then(data=>{
      overview=data;
      if(data.snapshot){
        const snap=data.snapshot;
        renderForward(snap.forward || []);
        const basket=snap.basket;
        if(settingsKey(settings()) === "1/1/10") {
          setText("candidate-status",`Prices through ${basket.date} · ${basket.risk_on?"Invested model":"Cash allocation"} · Daily refresh`);
          const list=$("candidate-positions");list.replaceChildren();
          if(basket.positions.length) basket.positions.forEach(p=>position(list,p.ticker,p.weight,"Model target weight"));
          else {const div=document.createElement("div");div.className="empty-state";div.textContent=basket.risk_on?"No eligible stocks with current data.":"Nifty trend filter indicates a 100% cash allocation.";list.append(div);}
        }
      } else {
        setText("candidate-status","Daily research snapshot pending. Refresh holdings to calculate on demand.");
      }
      renderResearchTables(data);updateIllustration();
    })
    .catch(e=>message("Could not load saved research data: "+e.message,true));
  }
  loadOverview();
  setInterval(loadOverview, 15 * 60 * 1000);
})();
