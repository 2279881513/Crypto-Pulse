function loadData(){
    // 非首次回测：保存参数后刷新页面，避免浏览器连接池耗尽
    if(loadCount>0){
        const params={style:currentStyle,lookahead:document.getElementById('sel-lookahead').value,start:document.getElementById('sel-start').value,end:document.getElementById('sel-end').value,dateRange:document.getElementById('date-range').value};
        sessionStorage.setItem('bk_params',JSON.stringify(params));
        location.reload();
        return;
    }
    loadCount++;
    // 停止自动刷新定时器，避免干扰
    if(latestTimer){clearInterval(latestTimer);latestTimer=null;}
    if(realtimeTimer){clearInterval(realtimeTimer);realtimeTimer=null;}
    // 取消上一次请求，释放连接
    if(loadAbort){
        try{loadAbort.abort();}catch(e){}
        loadAbort=null;
    }
    const ac=new AbortController();
    loadAbort=ac;
    const lookahead=document.getElementById('sel-lookahead').value;
    const start=document.getElementById('sel-start').value;
    const end=document.getElementById('sel-end').value;
    const dateRange=parseDateRange(document.getElementById('date-range'));
    if(dateRange)saveDateHistory(document.getElementById('date-range').value);
    const reqId=++loadReqId;
    const info=document.getElementById('tb-info');
    const startLabel=dateRange?dateRange.start:(start||'最早');
    const endLabel=dateRange?dateRange.end:(latestMode?'最新':(end||'现在'));
    info.textContent='⏳ 正在回测 '+startLabel+' ~ '+endLabel+' ...';
    document.getElementById('table-wrap').innerHTML='<div style="padding:30px;text-align:center;color:#525f7a;font-size:12px">⏳ 正在计算信号，请稍候...</div>';
    document.getElementById('load-err').style.display='none';
    // 估算K线数量和预计时间
    let totalEst=0;
    if(dateRange){
        const s=new Date(dateRange.start),e=new Date(dateRange.end);
        const days=(e-s)/(86400000);
        totalEst=Math.max(100,Math.round(days*1440));
    }else if(start&&end){
        const s=new Date(start),e=new Date(end);
        const days=(e-s)/(86400000);
        totalEst=Math.max(100,Math.round(days*1440));
    }else if(start&&latestMode){
        const s=new Date(start),e=new Date();
        const days=(e-s)/(86400000);
        totalEst=Math.max(100,Math.round(days*1440));
    }else{totalEst=10000;}
    // 估算时间：约 800 根/秒
    var estSec=Math.max(3,Math.round(totalEst/840));
    var startTime=Date.now();
    const barFill=document.querySelector('#progress-overlay .progress-bar-fill');
    const barText=document.getElementById('progress-text');
    document.getElementById('progress-overlay').classList.add('show');
    // 清除上一次的进度条定时器
    if(progTimer)clearInterval(progTimer);
    barFill.style.animation='none';barFill.style.width='0%';
    barText.textContent='正在回测 '+startLabel+' ~ '+endLabel+' ...';
    progTimer=setInterval(function(){
        var el=(Date.now()-startTime)/1000;
        var p=Math.min(95,Math.round(el/estSec*100));
        barFill.style.width=p+'%';
        var remaining=Math.max(0,Math.round(estSec-el));
        if(el>estSec*3){
            barText.textContent='⏳ 已处理 '+Math.round(el)+' 秒, 超出预计时间, 请查看后端控制台是否有报错';
        }else{
            barText.textContent='已处理 '+Math.round(el)+' 秒, 预计剩余 '+remaining+' 秒'+(totalEst?', 约 '+totalEst+' 根K线':'');
        }
    },300);
    let url='/api/backtest?style='+currentStyle+'&lookahead='+lookahead+'&_t='+Date.now();
    if(realtimeMode)url+='&trade_start='+realtimeStart;
    if(dateRange){url+='&start='+encodeURIComponent(dateRange.start);url+='&end='+encodeURIComponent(dateRange.end);}
    else{if(start)url+='&start='+start;if(!latestMode&&end)url+='&end='+end;}
    // 设置请求超时（超过300秒自动取消）
    const timeoutId=setTimeout(()=>ac.abort(), 300000);
    const xhr=new XMLHttpRequest();
    xhr.open('GET',url,true);
    xhr.responseType='json';
    xhr.onload=function(){
        clearTimeout(timeoutId);
        clearInterval(progTimer);
        // 释放旧数据
        candles=[];trades=[];stats=null;allSignals=[];
        barFill.style.width='100%';
        barText.textContent='处理完成 ✅';
        setTimeout(()=>{document.getElementById('progress-overlay').classList.remove('show');},300);
        if(reqId!==loadReqId)return;
        const d=xhr.response;
        if(!d||d.error){document.getElementById('load-err').style.display='flex';document.getElementById('err-detail').textContent=(d?d.error:'空响应');info.textContent='❌ '+(d?d.error:'空响应');return}
        candles=d.candles||[];trades=d.trades||[];stats=d.stats||{};allSignals=d.all_signals||[];window._cdZones=d.sl_cooldown_zones||[];
        lastPrediction=d.prediction||null;
        renderChart();renderStats();renderTable();renderDistChart();
        updateNetPnl();
        updatePosPanel();
        const icon=realtimeMode?'🔴 ':(latestMode?'📡 ':'✅ ');
        info.textContent=icon+d.total_candles+'根K线 · '+stats.total_trades+'笔交易';
        if(d.date_range)info.textContent+=' · '+d.date_range.start+'~'+d.date_range.end;
        if(lastPrediction){
            info.textContent+=' · 预测:'+(lastPrediction.direction==='bullish'?'📈':'📉')+lastPrediction.confidence+'%';
            document.getElementById('btn-histpred').style.borderColor='#667eea';
            document.getElementById('btn-histpred').style.color='#667eea';
        }
    };
    xhr.onerror=function(){clearInterval(progTimer);clearTimeout(timeoutId);document.getElementById('progress-overlay').classList.remove('show');if(reqId!==loadReqId)return;info.textContent='❌ 网络错误, 请刷新页面重试';document.getElementById('load-err').style.display='flex';document.getElementById('err-detail').innerHTML='网络请求失败<br><br>可能原因:<br>1. 服务器连接数已满<br>2. 浏览器连接池耗尽<br>3. 请<button onclick="location.reload()" style="padding:2px 8px;border:none;border-radius:3px;background:#667eea;color:#fff;cursor:pointer">刷新页面</button>后重试';};
    xhr.onabort=function(){clearInterval(progTimer);clearTimeout(timeoutId);document.getElementById('progress-overlay').classList.remove('show');};
    ac.signal.addEventListener('abort',function(){xhr.abort();});
    xhr.send();
}

// ===== 费用过滤：过滤利润不够扣手续费的低质量信号 =====
function getFilteredTrades(src){
    if(!document.getElementById('chk-fee-filter').checked)return src;
    const fee=parseFloat(document.getElementById('pos-fee').value)||0.0005;
    const minPnl=fee*2*100;
    return src.filter(t=>Math.abs(t.pnl_pct)>=minPnl);
}

// checkbox 变化时刷新
['pos-fee','chk-fee-filter'].forEach(id=>{
    const el=document.getElementById(id);
    if(el)el.addEventListener('change',()=>{
        if(trades&&trades.length){renderChart(true);renderStats();renderTable();renderDistChart();renderScoreChart();updatePosPanel();updateNetPnl();}
    });
});

function updateNetPnl(){
    try{
    const ft=getFilteredTrades(trades);
    const el=document.getElementById('st-pnl-net');
    if(!ft||!ft.length){el.innerHTML='';return}
    const cap=parseFloat(document.getElementById('pos-capital').value)||1000;
    const lev=parseFloat(document.getElementById('pos-leverage').value)||1;
    const fee=parseFloat(document.getElementById('pos-fee').value)||0.0005;
    const grossPnl=ft.reduce(function(s,t){return s+t.pnl_pct},0);
    const totalFee=ft.length*cap*lev*fee*2;
    const net=grossPnl*cap*lev/100-totalFee;
    const roi=net/cap*100;
    if(net>=0)el.innerHTML='<span style="color:#2ecc71">净利 +$'+net.toFixed(0)+' ROI +'+roi.toFixed(1)+'%</span>';
    else el.innerHTML='<span style="color:#e74c3c">净利 -$'+Math.abs(net).toFixed(0)+' ROI '+roi.toFixed(1)+'%</span>';
    }catch(e){}
}
function fmtPct(a,b){try{var r=((Number(a)/Number(b))-1)*100;return isNaN(r)?'':(r>=0?'+':'')+r.toFixed(2)+'%'}catch(e){return''}}

// ===== 仓位管理 =====
['pos-capital','pos-leverage','pos-fee'].forEach(id=>{
    const el=document.getElementById(id);
    if(el)el.addEventListener('change',()=>{
        localStorage.setItem('cryptopulse_settings',JSON.stringify({
            capital:parseFloat(document.getElementById('pos-capital').value)||1000,
            leverage:parseFloat(document.getElementById('pos-leverage').value)||1,
            feeRate:document.getElementById('pos-fee').value,
        }));
        // 更新净利显示
        if(typeof stats!=='undefined'&&stats&&stats.total_trades){
            const cap=parseFloat(document.getElementById('pos-capital').value)||1000;
            const lev=parseFloat(document.getElementById('pos-leverage').value)||1;
            const fee=parseFloat(document.getElementById('pos-fee').value)||0.0005;
            const gross=stats.total_pnl_pct||0;
            const totalFee=stats.total_trades*cap*lev*fee*2;
            const net=gross*cap*lev/100-totalFee;
            const roi=net/cap*100;
            const el=document.getElementById('st-pnl-net');
            if(net>=0)el.innerHTML='<span style="color:#2ecc71">净利 +$'+net.toFixed(0)+' ROI +'+roi.toFixed(1)+'%</span>';
            else el.innerHTML='<span style="color:#e74c3c">净利 -$'+Math.abs(net).toFixed(0)+' ROI '+roi.toFixed(1)+'%</span>';
        }
    });
});

function updatePosPanel(){
    const ft=getFilteredTrades(trades);
    if(!ft||!ft.length){document.getElementById('pos-panel').innerHTML='<div style="text-align:center;color:#525f7a;padding:30px">暂无交易数据</div>';return}
    const cap=parseFloat(document.getElementById('pos-capital').value)||1000;
    const lev=parseFloat(document.getElementById('pos-leverage').value)||1;
    const fee=parseFloat(document.getElementById('pos-fee').value)||0.0005;
    const wins=ft.filter(t=>t.pnl_pct>0).length;
    const losses=ft.filter(t=>t.pnl_pct<=0).length;
    const grossPnl=ft.reduce((s,t)=>s+t.pnl_pct,0);
    const totalFee=ft.length*cap*lev*fee*2;
    const netPnl=grossPnl*cap*lev/100-totalFee;
    const roi=netPnl/cap*100;
    const avgWin=ft.filter(t=>t.pnl_pct>0).reduce((s,t)=>s+t.pnl_pct,0)/Math.max(1,wins);
    const avgLoss=ft.filter(t=>t.pnl_pct<=0).reduce((s,t)=>s+t.pnl_pct,0)/Math.max(1,losses);
    const sgn=n=>n>0?'+':'';
    const c=n=>n>=0?'#2ecc71':'#e74c3c';
    document.getElementById('pos-panel').innerHTML='<div style="max-width:100%">'
        +'<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:6px">'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">本金</div><div style="font-size:14px;font-weight:700;font-family:monospace">$'+cap.toFixed(0)+'</div></div>'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">杠杆</div><div style="font-size:14px;font-weight:700;font-family:monospace">'+lev+'x</div></div>'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">费率</div><div style="font-size:14px;font-weight:700;font-family:monospace">'+(fee*100).toFixed(2)+'%</div></div>'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">笔数</div><div style="font-size:14px;font-weight:700;font-family:monospace">'+trades.length+'</div></div>'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">胜/负</div><div style="font-size:14px;font-weight:700;font-family:monospace">'+wins+'/'+losses+'</div></div>'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">胜率</div><div style="font-size:14px;font-weight:700;font-family:monospace;color:#2ecc71">'+(wins/trades.length*100).toFixed(1)+'%</div></div>'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">总毛利</div><div style="font-size:14px;font-weight:700;font-family:monospace;color:'+c(grossPnl)+'">'+sgn(grossPnl)+grossPnl.toFixed(2)+'%</div></div>'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">手续费</div><div style="font-size:14px;font-weight:700;font-family:monospace;color:#e74c3c">$'+totalFee.toFixed(2)+'</div></div>'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">净利润</div><div style="font-size:14px;font-weight:700;font-family:monospace;color:'+c(netPnl)+'">'+sgn(netPnl)+'$'+Math.abs(netPnl).toFixed(2)+'</div></div>'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">ROI</div><div style="font-size:14px;font-weight:700;font-family:monospace;color:'+c(roi)+'">'+sgn(roi)+roi.toFixed(2)+'%</div></div>'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">平均盈</div><div style="font-size:14px;font-weight:700;font-family:monospace;color:#2ecc71">'+sgn(avgWin)+avgWin.toFixed(3)+'%</div></div>'
        +'<div style="background:#131a2b;border-radius:4px;padding:8px;text-align:center"><div style="color:#525f7a;font-size:9px">平均亏</div><div style="font-size:14px;font-weight:700;font-family:monospace;color:#e74c3c">'+avgLoss.toFixed(3)+'%</div></div>'
        +'</div>'
        +'</div>';
}

function toggleHistPred(){
    showHistPred=!showHistPred;
    const btn=document.getElementById('btn-histpred');
    btn.style.background=showHistPred?'#667eea':'transparent';
    btn.style.color=showHistPred?'#fff':'#525f7a';
    btn.style.borderColor=showHistPred?'#667eea':'#525f7a';
    if(showHistPred)renderPrediction();
    else{predSeries.setData([]);histPredSeries.setData([]);}
}

function renderPrediction(){
    if(!candles||candles.length<2){predSeries.setData([]);histPredSeries.setData([]);return}
    // 历史预测K线：所有有信号的K线的预测
    const histData=[];
    const signals=candles.filter(c=>c.s&&c.s.direction&&c.s.direction!=='neutral');
    for(let j=0;j<signals.length;j++){
        const s=signals[j];
        const atr=(s.h-s.l)||1;
        const open=s.c;
        const isUp=s.s.direction==='bullish';
        const predTime=Math.floor(s.t/1000)+60;
        let close,high,low;
        if(isUp){close=open+atr*0.4;high=Math.max(open,close)+atr*0.2;low=Math.min(open,close)-atr*0.2;}
        else{close=open-atr*0.4;high=Math.max(open,close)+atr*0.2;low=Math.min(open,close)-atr*0.2;}
        histData.push({time:predTime,open,high,low,close});
    }
    histPredSeries.setData(histData.length?histData:[]);
    // 下一条预测K线
    if(lastPrediction){
        const last=candles[candles.length-1];
        const nextTime=last.t+60000;
        const base=last.c;
        const atr=Math.abs(last.h-last.l);
        const range=Math.max(atr*0.5,base*0.002);
        const isBull=lastPrediction.direction==='bullish';
        const predOpen=base+(isBull?range*0.1:-range*0.1);
        const predClose=base+(isBull?range*0.6:-range*0.6);
        const predHigh=base+(isBull?range*0.8:-range*0.2);
        const predLow=base+(isBull?range*0.05:-range*0.8);
        predSeries.setData([{time:nextTime/1000,open:predOpen,high:predHigh,low:predLow,close:predClose}]);
        chart.timeScale().scrollToPosition(chart.timeScale().scrollPosition()+30,false);
    }else{predSeries.setData([]);}
}

// 绘制止损冷却区间（橙色柱状条，在成交量位置）
function renderCooldownZones() {
    if (!cdZoneSeries) return;
    if (!window._cdZones || !window._cdZones.length) {
        cdZoneSeries.setData([]);
        return;
    }
    // 为冷却区间内的每根K线生成一个数据点（用成交量单位的值）
    const zoneMap = {}; // timestamp -> should highlight
    window._cdZones.forEach(zone => {
        const startSec = Math.floor(zone.start_ts / 1000);
        const endSec = Math.floor(zone.end_ts / 1000);
        // 标记范围内所有K线
        candles.forEach(c => {
            const t = Math.floor(c.t / 1000);
            if (t >= startSec && t <= endSec) {
                zoneMap[t] = true;
            }
        });
    });
    // 生成柱状数据：在冷却区间的K线显示橙色柱
    const cdData = [];
    candles.forEach(c => {
        const t = Math.floor(c.t / 1000);
        if (zoneMap[t]) {
            cdData.push({ time: t, value: c.v * 0.5, color: 'rgba(255,152,0,0.35)' });
        }
    });
    cdZoneSeries.setData(cdData);
}

function renderChart(keepZoom){
    if(!candles||!candles.length){candleSeries.setData([]);volumeSeries.setData([]);candleSeries.setMarkers([]);return}
    // 保存缩放位置
    let savedPos=null,savedRight=null;
    if(keepZoom){
        try{savedPos=chart.timeScale().scrollPosition();savedRight=chart.timeScale().getVisibleLogicalRange();}catch(e){}
    }
    const cdlData=candles.map(c=>({time:Math.floor(c.t/1000),open:c.o,high:c.h,low:c.l,close:c.c}));
    candleSeries.setData(cdlData);
    volumeSeries.setData(candles.map(c=>({time:Math.floor(c.t/1000),value:c.v,color:c.c>=c.o?'rgba(46,204,113,0.25)':'rgba(231,76,60,0.25)'})));
    const markers=[],tradeMap={},signalColors={};
    const markersTrades=getFilteredTrades(trades);
    markersTrades.forEach(t=>tradeMap[t.timestamp]=t);
    const feeFilterOn=document.getElementById('chk-fee-filter').checked;
    // 检查信号是否被风控阻止（回测数据中的 risk_blocked 或 live 冷却状态）
    function isRiskBlocked(c) {
        if (c.s && c.s.risk_blocked) return true;
        if (!btRiskStatus) return false;
        if (!btRiskStatus.in_sl_cooldown) return false;
        return true;
    }
    candles.forEach(c=>{
        if(!c.s||c.s.direction==='neutral')return;
        const t=Math.floor(c.t/1000);
        const tr=tradeMap[c.t];
        const isRisk = isRiskBlocked(c);

        // ---- 风控高亮模式：只显示匹配的风控信号 ----
        if(highlightFilter && highlightFilter.type==='risk') {
            if(!isRisk) return;  // 非风控信号全隐藏
            if((c.s.risk_reason||'') !== highlightFilter.value) return; // 不匹配的风控原因隐藏
            const dir=c.s.direction==='bullish';
            markers.push({time:t,position:dir?'belowBar':'aboveBar',color:'#ff9800',shape:dir?'arrowUp':'arrowDown',text:'⛔',size:2.0});
            return;
        }

        // ---- 评分/离场原因高亮：非交易全隐藏，只显匹配 ----
        if(highlightFilter && (highlightFilter.type==='score'||highlightFilter.type==='reason'||highlightFilter.type==='timeout_result')) {
            if(!tr) return;
            let matched=true;
            if(highlightFilter.type==='reason') matched=(tr.exit_reason||'时间到')===highlightFilter.value;
            else if(highlightFilter.type==='score'){
                const bucket=Math.floor(Math.abs(tr.score)/10)*10;
                matched=bucket===highlightFilter.value;
            }else if(highlightFilter.type==='timeout_result'){
                const isTimeout=(tr.exit_reason==='超时'||tr.exit_reason==='时间到');
                if(!isTimeout) return;
                matched=highlightFilter.value==='profit'?tr.pnl_pct>0:tr.pnl_pct<=0;
            }
            if(!matched) return;
            const isUp=tr.direction==='bullish';
            const isGreen=tr.correct;
            markers.push({time:t,position:isUp?'belowBar':'aboveBar',color:isGreen?'#2ecc71':'#e74c3c',shape:isUp?'arrowUp':'arrowDown',text:isGreen?'✅':'❌',size:2.0});
            return;
        }

        if(tr){
            const isUp=tr.direction==='bullish';
            const isGreen=tr.correct;
            markers.push({time:t,position:isUp?'belowBar':'aboveBar',color:isGreen?'#2ecc71':'#e74c3c',shape:isUp?'arrowUp':'arrowDown',text:isGreen?'✅':'❌',size:1.5});
        }else{
            const filteredOut = feeFilterOn && trades.some(tr2 => tr2.timestamp === c.t);
            if(filteredOut){
                const dir=c.s.direction==='bullish';
                markers.push({time:t,position:dir?'belowBar':'aboveBar',color:'#525f7a',shape:dir?'arrowUp':'arrowDown',text:'',size:1.2});
            }else if(isRiskBlocked(c)){
                // 风控阻止：做多被阻→橙色向上箭头，做空被阻→橙色向下箭头
                const dir=c.s.direction==='bullish';
                markers.push({time:t,position:dir?'belowBar':'aboveBar',color:'#ff9800',shape:dir?'arrowUp':'arrowDown',text:'⛔',size:1.2});
            }else{
                markers.push({time:t,position:'inBar',color:'#525f7a',shape:'diamond',text:'',size:0.6});
            }
        }
    });
    candleSeries.setMarkers(markers);
    // 绘制冷却区间
    renderCooldownZones();
    if(showHistPred)renderPrediction();
    // 高亮状态指示
    const hlLabel=document.getElementById('hl-label');
    if(highlightFilter){
        const val=highlightFilter.value;
        const txt=highlightFilter.type==='reason'?val:(highlightFilter.type==='risk'?'风控:'+val:(highlightFilter.type==='timeout_result'?(val==='profit'?'超时盈利':'超时亏损'):(val+'~'+(val+10)+'分')));
        hlLabel.textContent='🔍 '+txt;
        hlLabel.style.display='block';
    }else{
        hlLabel.style.display='none';
    }
    if(keepZoom&&savedPos!==null){
        try{chart.timeScale().setVisibleLogicalRange(savedRight);}catch(e){chart.timeScale().fitContent();}
    }else{
        chart.timeScale().scrollToRealTime();
    }
}

function jumpToTrade(ts){
    const timeSec=Math.floor(ts/1000);
    let idx=-1;
    for(let i=0;i<candles.length;i++){
        if(Math.floor(candles[i].t/1000)===timeSec){idx=i;break}
    }
    if(idx<0){for(let i=0;i<candles.length;i++){
        if(Math.abs(Math.floor(candles[i].t/1000)-timeSec)<60){idx=i;break}
    }}
    if(idx>=0){
        const visibleCount=80;
        const start=Math.max(0,idx-visibleCount/2);
        const end=Math.min(candles.length-1,start+visibleCount);
        const fromTime=Math.floor(candles[start].t/1000);
        const toTime=Math.floor(candles[end].t/1000);
        chart.timeScale().setVisibleRange({from:fromTime,to:toTime});
        // 闪烁：先保存当前标记，显示闪烁标记，1.5秒后恢复
        const flash=[{time:timeSec,position:'inBar',color:'#f1c40f',shape:'circle',text:'⭐',size:2.5}];
        candleSeries.setMarkers(flash);
        setTimeout(()=>{
            // 恢复原始标记（不触发重新渲染，避免scrollToRealTime）
            const origMarkers=[];
            const tradeMap={};
            trades.forEach(t=>tradeMap[t.timestamp]=t);
            candles.forEach(c=>{
                if(!c.s||c.s.direction==='neutral')return;
                const ct=Math.floor(c.t/1000);
                const tr=tradeMap[c.t];
                if(highlightFilter){
                    let matched=true;
                    if(highlightFilter.type==='reason')matched=(tr.exit_reason||'超时')===highlightFilter.value;
                    else if(highlightFilter.type==='score'){const bucket=Math.floor(Math.abs(tr.score)/10)*10;matched=bucket===highlightFilter.value;}
                    if(!matched)return;
                }
                if(tr){
                    const isUp=tr.direction==='bullish';
                    origMarkers.push({time:ct,position:isUp?'belowBar':'aboveBar',color:tr.correct?'#2ecc71':'#e74c3c',shape:isUp?'arrowUp':'arrowDown',text:tr.correct?'✅':'❌',size:highlightFilter?2.0:1.5});
                }else{
                    origMarkers.push({time:ct,position:'inBar',color:'#525f7a',shape:'diamond',text:'',size:0.6});
                }
            });
            candleSeries.setMarkers(origMarkers);
        },1500);
    }
}

function renderStats(){
    // 费用过滤开启时：用过滤后的trades重算stats
    const feeFilterOn=document.getElementById('chk-fee-filter').checked;
    let useStats=stats;
    if(feeFilterOn&&trades&&trades.length){
        const ft=getFilteredTrades(trades);
        const total=ft.length;
        if(!total){document.getElementById('st-total').textContent='0 (过滤)';return}
        useStats={
            total_trades:total,
            correct:ft.filter(t=>t.correct).length,
            wrong:total-ft.filter(t=>t.correct).length,
            accuracy:Math.round(ft.filter(t=>t.correct).length/total*1000)/10,
            total_pnl_pct:ft.reduce((s,t)=>s+t.pnl_pct,0),
            win_rate:Math.round(ft.filter(t=>t.pnl_pct>0).length/total*1000)/10,
        };
        const wins=ft.filter(t=>t.pnl_pct>0);
        const losses=ft.filter(t=>t.pnl_pct<=0);
        useStats.avg_win=wins.length?Math.round(ft.filter(t=>t.pnl_pct>0).reduce((s,t)=>s+t.pnl_pct,0)/wins.length*100)/100:0;
        useStats.avg_loss=losses.length?Math.round(ft.filter(t=>t.pnl_pct<=0).reduce((s,t)=>s+t.pnl_pct,0)/losses.length*100)/100:0;
        useStats.profit_factor=losses.length?Math.round(Math.abs(ft.filter(t=>t.pnl_pct>0).reduce((s,t)=>s+t.pnl_pct,0)/ft.filter(t=>t.pnl_pct<=0).reduce((s,t)=>s+t.pnl_pct,0))*100)/100:0;
        useStats.bullish=ft.filter(t=>t.direction==='bullish').length;
        useStats.bearish=ft.filter(t=>t.direction==='bearish').length;
        useStats.correct_bullish=ft.filter(t=>t.direction==='bullish'&&t.correct).length;
        useStats.correct_bearish=ft.filter(t=>t.direction==='bearish'&&t.correct).length;
        // 连赢连亏
        let cw=0,cl=0,mcw=0,mcl=0;
        ft.forEach(t=>{if(t.pnl_pct>0){cw++;cl=0;mcw=Math.max(mcw,cw);}else{cl++;cw=0;mcl=Math.max(mcl,cl);}});
        useStats.max_consecutive_wins=mcw;
        useStats.max_consecutive_losses=mcl;
    }
    if(!useStats||!useStats.total_trades){
        document.getElementById('st-total').textContent=realtimeMode?'0 (实时)':'0';
        document.getElementById('st-accuracy').textContent='--%';
        document.getElementById('st-bullish').innerHTML='📈 0/0';
        document.getElementById('st-bearish').innerHTML='📉 0/0';
        document.getElementById('st-correct').textContent='0';
        document.getElementById('st-wrong').textContent='0';
        document.getElementById('st-pnl').textContent='--%';
        document.getElementById('st-winrate').textContent='0%';
        document.getElementById('st-profitfactor').textContent='--';
        document.getElementById('st-avgwin').textContent='--%';
        document.getElementById('st-avgloss').textContent='--%';
        document.getElementById('st-conwins').textContent='--';
        document.getElementById('st-conlosses').textContent='--';
        return
    }
    const prefix=realtimeMode?'🔴 ':'✅ ';
    document.getElementById('st-total').textContent=prefix+useStats.total_trades;
    document.getElementById('st-bullish').innerHTML='📈 '+useStats.correct_bullish+'/'+useStats.bullish;
    document.getElementById('st-bearish').innerHTML='📉 '+useStats.correct_bearish+'/'+useStats.bearish;
    document.getElementById('st-correct').textContent=useStats.correct;
    document.getElementById('st-wrong').textContent=useStats.wrong;
    const acc=document.getElementById('st-accuracy');acc.textContent=Number(useStats.accuracy).toFixed(1)+'%';acc.style.color=useStats.accuracy>=60?'#2ecc71':(useStats.accuracy>=40?'#f1c40f':'#e74c3c');
    const pnl=document.getElementById('st-pnl');pnl.textContent=(useStats.total_pnl_pct>=0?'+':'')+Number(useStats.total_pnl_pct).toFixed(2)+'%';pnl.style.color=useStats.total_pnl_pct>=0?'#2ecc71':'#e74c3c';
    document.getElementById('st-winrate').textContent=useStats.win_rate+'%';
    document.getElementById('st-profitfactor').textContent=Number(useStats.profit_factor).toFixed(2);
    document.getElementById('st-avgwin').textContent=(useStats.avg_win>=0?'+':'')+Number(useStats.avg_win).toFixed(2)+'%';
    document.getElementById('st-avgloss').textContent=Number(useStats.avg_loss).toFixed(2)+'%';
    document.getElementById('st-conwins').textContent=useStats.max_consecutive_wins;
    document.getElementById('st-conlosses').textContent=useStats.max_consecutive_losses;
}

function renderTable(){
    const ft=getFilteredTrades(trades);
    if(!ft.length){document.getElementById('table-wrap').innerHTML='<div style="padding:20px;text-align:center;color:#525f7a">暂无交易数据</div>';return}
    const sorted=[...ft].reverse();
    let html='<table><thead><tr><th style="width:24px">#</th><th style="width:75px">时间</th><th>方向</th><th>评分</th><th>入场价</th><th style="color:#e74c3c">止损</th><th>出场价</th><th>PnL%</th><th>结果</th><th>原因</th></tr></thead><tbody>';
    sorted.forEach((t,i)=>{
        const dirCls=t.direction==='bullish'?'td-up':'td-down',dirTxt=t.direction==='bullish'?'📈 多':'📉 空';
        const pnlCls=t.pnl_pct>=0?'td-pnl-pos':'td-pnl-neg',pnlTxt=(t.pnl_pct>=0?'+':'')+t.pnl_pct+'%';
        const resCls=t.correct?'td-ok':'td-fail',resTxt=t.correct?'✅':'❌';
        const slTxt=t.sl_price?t.sl_price.toFixed(1):'--';
        html+='<tr onclick="jumpToTrade('+t.timestamp+')" style="cursor:pointer"><td class="td-time">'+(sorted.length-i)+'</td><td class="td-time">'+t.time+'</td><td class="'+dirCls+'">'+dirTxt+'</td><td class="td-num">'+Math.abs(t.score)+'</td><td class="td-price">'+t.entry_price+'</td><td class="td-price" style="color:#e74c3c">'+slTxt+'</td><td class="td-price">'+t.exit_price+'</td><td class="'+pnlCls+'">'+pnlTxt+'</td><td class="'+resCls+'">'+resTxt+'</td><td style="font-size:9px;color:#525f7a;white-space:nowrap">'+(t.exit_reason||'')+'</td></tr>';
    });
    document.getElementById('table-wrap').innerHTML=html+'</tbody></table>';
}

function renderDistChart(){
    const ft=getFilteredTrades(trades);
    if(!ft.length){document.getElementById('dist-chart').innerHTML='<div style="padding:20px;text-align:center;color:#525f7a">暂无交易数据</div>';return}
    const pnls=ft.map(t=>t.pnl_pct),minPnl=Math.floor(Math.min(...pnls)),maxPnl=Math.ceil(Math.max(...pnls));
    const binCount=Math.max(10,Math.min(30,Math.ceil((maxPnl-minPnl)/0.5))),binWidth=(maxPnl-minPnl)/binCount||0.1;
    const bins=[];for(let i=0;i<binCount;i++){const lo=minPnl+i*binWidth,hi=lo+binWidth;bins.push({lo,hi,count:pnls.filter(p=>p>=lo&&(i===binCount-1?p<=hi:p<hi)).length,isWin:lo>=0})}
    const maxCount=Math.max(...bins.map(b=>b.count),1);
    let html='<div style="padding:4px 0;font-size:10px;color:#525f7a;margin-bottom:4px">PnL 分布（共 '+trades.length+' 笔）</div>';
    const wins=pnls.filter(p=>p>0).length,losses=pnls.filter(p=>p<=0).length;
    html+='<div style="display:flex;gap:14px;margin-bottom:6px;font-size:10px"><span style="color:#2ecc71">✅ 盈利 '+wins+' 笔</span><span style="color:#e74c3c">❌ 亏损 '+losses+' 笔</span></div>';
    bins.forEach(b=>{const pct=b.count/maxCount*100;html+='<div class="dist-bar-wrap"><span class="dist-label">'+(b.lo>=0?'+':'')+b.lo.toFixed(1)+'%</span><div class="dist-bar-bg"><div class="dist-bar-fill" style="width:'+Math.max(pct,5)+'%;background:'+(b.isWin?'#2ecc71':'#e74c3c')+'">'+(b.count>0?b.count:'')+'</div></div><span class="dist-count">'+b.count+'</span></div>'});
    let cumPnl=0;const cumData=trades.map(t=>{cumPnl+=t.pnl_pct;return{cum:Math.round(cumPnl*100)/100}});
    const maxCum=Math.max(...cumData.map(d=>d.cum),1),minCum=Math.min(...cumData.map(d=>d.cum),-1),cumRange=maxCum-minCum||1;
    html+='<div style="margin-top:10px;font-size:10px;color:#525f7a">PnL 累积曲线</div><div style="display:flex;align-items:flex-end;height:40px;gap:1px;padding:2px 0">';
    cumData.forEach(d=>{const h=((d.cum-minCum)/cumRange)*36;html+='<div style="width:3px;height:'+Math.max(h,1)+'px;background:'+(d.cum>=0?'#2ecc71':'#e74c3c')+';border-radius:1px;flex-shrink:0"></div>'});
    html+='</div><div style="display:flex;justify-content:space-between;font-size:8px;color:#525f7a"><span>起始</span><span>最终: '+(cumData.length?(cumData[cumData.length-1].cum>=0?'+':'')+cumData[cumData.length-1].cum+'%':'0%')+'</span></div>';
    document.getElementById('dist-chart').innerHTML=html;
}

function renderScoreChart(){
    const ft=getFilteredTrades(trades);
    if(!ft.length){document.getElementById('score-panel').innerHTML='<div style="padding:20px;text-align:center;color:#525f7a">暂无交易数据</div>';return}
    const byScore={};
    ft.forEach(t=>{
        const b=Math.floor(Math.abs(t.score)/10)*10;
        if(!byScore[b])byScore[b]={total:0,correct:0,wrong:0};
        byScore[b].total++;
        if(t.correct)byScore[b].correct++;else byScore[b].wrong++;
    });
    const keys=Object.keys(byScore).map(Number).sort((a,b)=>a-b);
    const maxTotal=Math.max(...keys.map(k=>byScore[k].total),1);
    let html='<div style="padding:4px 0;font-size:10px;color:#525f7a;margin-bottom:4px">评分分布</div>';
    keys.forEach(k=>{
        const d=byScore[k];
        const acc=d.total>0?Math.round(d.correct/d.total*100):0;
        const w=Math.max(d.total/maxTotal*100,5);
        const barColor=acc>=60?'#2ecc71':(acc>=40?'#f1c40f':'#e74c3c');
        const selected=(highlightFilter&&highlightFilter.type==='score'&&highlightFilter.value===k);
        html+='<div class="dist-bar-wrap" style="cursor:pointer;opacity:'+(highlightFilter&&!selected?0.4:1)+'" onclick="setHighlight(\'score\',"+k+")"><span class="dist-label">'+k+'~'+(k+10)+'</span>'
            +'<div class="dist-bar-bg"><div class="dist-bar-fill" style="width:'+w+'%;background:'+barColor+'">'+d.total+'</div></div>'
            +'<span style="font-size:9px;color:#8892b0;width:40px;text-align:left">'+(d.correct>0?'<span style="color:#2ecc71">'+d.correct+'</span>/':'')+(d.wrong>0?'<span style="color:#e74c3c">'+d.wrong+'</span>':'')+'</span>'
            +'<span style="font-size:9px;color:'+barColor+';width:30px;text-align:left">'+acc+'%</span></div>';
    });
    html+='<div style="margin-top:8px;font-size:10px;color:#525f7a">离场原因分布</div>';
    const reasons={};
    const timeoutProfit={total:0,profit:0,loss:0};
    ft.forEach(t=>{
        const r=t.exit_reason||'时间到';
        if(r==='超时'||r==='时间到'){
            timeoutProfit.total++;
            if(t.pnl_pct>0)timeoutProfit.profit++;else timeoutProfit.loss++;
        }else{
            if(!reasons[r])reasons[r]=0;
            reasons[r]++;
        }
    });
    Object.keys(reasons).sort((a,b)=>reasons[b]-reasons[a]).forEach(r=>{
        const pct=Math.round(reasons[r]/ft.length*100);
        const icon=r==='止盈'?'🎯':(r==='止损'?'🛑':'⏱️');
        html+='<div class="dist-bar-wrap" style="cursor:pointer" onclick="setHighlight(\'reason\',\''+r+'\')"><span class="dist-label" style="width:60px">'+icon+r+'</span><div class="dist-bar-bg"><div class="dist-bar-fill" style="width:'+pct+'%;background:#525f7a">'+reasons[r]+'</div></div><span class="dist-count">'+pct+'%</span></div>';
    });
    // 超时细分：盈利/亏损
    if(timeoutProfit.total>0){
        const tpct=Math.round(timeoutProfit.total/ft.length*100);
        const ppct=timeoutProfit.total>0?Math.round(timeoutProfit.profit/timeoutProfit.total*100):0;
        html+='<div class="dist-bar-wrap" style="cursor:pointer" onclick="setHighlight(\'reason\',\'超时\')"><span class="dist-label" style="width:60px;font-size:10px;color:#8892b0">⏱️ 超时</span><div class="dist-bar-bg"><div class="dist-bar-fill" style="width:'+tpct+'%;background:#525f7a">'+timeoutProfit.total+'</div></div><span class="dist-count">'+tpct+'%</span></div>';
        html+='<div style="padding-left:64px;display:flex;gap:10px;font-size:9px;margin-bottom:4px">';
        html+='<span style="color:#2ecc71;cursor:pointer" onclick="setTimeoutHighlight(\'profit\')" title="点击高亮超时盈利">✅ 盈利 '+timeoutProfit.profit+' ('+(timeoutProfit.total>0?Math.round(timeoutProfit.profit/timeoutProfit.total*100):0)+'%)</span>';
        html+='<span style="color:#e74c3c;cursor:pointer" onclick="setTimeoutHighlight(\'loss\')" title="点击高亮超时亏损">❌ 亏损 '+timeoutProfit.loss+' ('+(timeoutProfit.total>0?Math.round(timeoutProfit.loss/timeoutProfit.total*100):0)+'%)</span>';
        html+='</div>';
    }
    html+='<div style="margin-top:4px;font-size:9px;color:#525f7a">点击可高亮K线图中的对应交易</div>';
    if(highlightFilter)html+='<div style="margin-top:4px"><button onclick="clearHighlight()" style="padding:2px 8px;border:none;border-radius:3px;font-size:10px;background:#667eea;color:#fff;cursor:pointer">清除高亮</button></div>';
    document.getElementById('score-panel').innerHTML=html;
}

function setHighlight(type,value){
    highlightFilter={type,value};
    renderChart(true);
    renderScoreChart();
}

function setTimeoutHighlight(result){
    setHighlight('timeout_result',result);
}

function clearHighlight(){
    highlightFilter=null;
    renderChart(true);
    renderScoreChart();
    // 如果当前是风控标签页也刷新
    if(document.getElementById('risk-panel').style.display==='block')renderRiskPanel();
}

function switchTab(tab){
    document.querySelectorAll('.panel-tab').forEach(el=>el.classList.remove('active'));
    document.querySelector('.panel-tab[data-tab="'+tab+'"]').classList.add('active');
    document.getElementById('table-wrap').style.display=tab==='list'?'block':'none';
    document.getElementById('dist-chart').style.display=tab==='dist'?'block':'none';
    document.getElementById('pos-panel').style.display=tab==='pos'?'block':'none';
    document.getElementById('score-panel').style.display=tab==='score'?'block':'none';
    document.getElementById('signal-panel').style.display=tab==='signal'?'block':'none';
    document.getElementById('risk-panel').style.display=tab==='risk'?'block':'none';
    if(tab==='pos')updatePosPanel();
    if(tab==='score')renderScoreChart();
    if(tab==='signal')renderSignalDetail();
    if(tab==='risk')renderRiskPanel();
}

function renderSignalDetail(){
    var el=document.getElementById('signal-panel');
    if(!stats){el.innerHTML='<div style="text-align:center;color:#525f7a;padding:20px">加载中...</div>';return}
    var s=stats;
    var tot=s.signal_total||0,bull=s.signal_bullish||0,bear=s.signal_bearish||0,neu=s.signal_neutral||0;
    var bP=bull&&tot?(bull/tot*100).toFixed(1):'0',beP=bear&&tot?(bear/tot*100).toFixed(1):'0',nP=neu&&tot?(neu/tot*100).toFixed(1):'0';
    var html='<div style="padding:14px">'
        +'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:14px">'
        +'<div style="background:#131a2b;border-radius:6px;padding:12px;text-align:center"><div style="font-size:24px;font-weight:700;color:#667eea">'+tot+'</div><div style="color:#525f7a;font-size:11px;margin-top:4px">总信号数</div></div>'
        +'<div style="background:#131a2b;border-radius:6px;padding:12px;text-align:center"><div style="font-size:24px;font-weight:700;color:#2ecc71">'+bull+'</div><div style="color:#525f7a;font-size:11px;margin-top:4px">做多 ('+bP+'%)</div></div>'
        +'<div style="background:#131a2b;border-radius:6px;padding:12px;text-align:center"><div style="font-size:24px;font-weight:700;color:#e74c3c">'+bear+'</div><div style="color:#525f7a;font-size:11px;margin-top:4px">做空 ('+beP+'%)</div></div>'
        +'</div>'
        +'<div style="background:#131a2b;border-radius:6px;padding:14px">'
        +'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1a2340"><span style="color:#525f7a">观望</span><span style="color:#e8edf5;font-weight:600">'+neu+' ('+nP+'%)</span></div>'
        +'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1a2340"><span style="color:#525f7a">做多占比</span><span style="color:#2ecc71;font-weight:600">'+bP+'%</span></div>'
        +'<div style="display:flex;justify-content:space-between;padding:6px 0"><span style="color:#525f7a">做空占比</span><span style="color:#e74c3c;font-weight:600">'+beP+'%</span></div>'
        +'</div></div>';
    el.innerHTML=html;
}

// ---- 风控显示 ----
