function parseDateRange(input){
    const val=input.value.trim();
    if(!val||!val.includes('-'))return null;
    const parts=val.split('-').map(s=>s.trim());
    if(parts.length!==2)return null;
    const fmt=s=>{
        // 支持 2026/05/01 00:00 和 2026-05-01T00:00 格式
        let str=s.replace(/\//g,'-');
        if(str.includes(' ')&&!str.includes('T'))str=str.replace(' ','T');
        if(!str.includes('T')&&str.length<=10)str+='T00:00';
        return str;
    };
    return {start:fmt(parts[0]),end:fmt(parts[1])};
}

function initDates(){
    const now=new Date();
    const fmt=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T'+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
    document.getElementById('sel-end').value=fmt(now);
    document.getElementById('sel-start').value=fmt(new Date(now.getTime()-24*3600*1000));
    initDateHistory();
}

function setRange(days){
    if(latestMode)toggleLatest();
    const now=new Date();
    const fmt=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T'+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
    document.getElementById('sel-end').value=fmt(now);
    document.getElementById('sel-start').value=fmt(new Date(now.getTime()-days*24*3600*1000));
    document.getElementById('date-range').value='';
    loadData();
}

function toggleLatest(){
    latestMode=!latestMode;
    const btn=document.getElementById('btn-latest');
    const endInput=document.getElementById('sel-end');
    if(latestMode){
        btn.style.background='#667eea';btn.style.color='#fff';
        endInput.disabled=true;endInput.style.opacity='0.4';
        // 设置结束时间为明天，让API用当前时间
        const d=new Date();d.setDate(d.getDate()+1);
        endInput.value=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T00:00';
        loadData();
        // 每60秒自动刷新
        if(latestTimer)clearInterval(latestTimer);
        latestTimer=setInterval(()=>{if(latestMode)silentReload();},30000);
    }else{
        btn.style.background='#1e2a45';btn.style.color='#8892b0';
        endInput.disabled=false;endInput.style.opacity='1';
        if(latestTimer){clearInterval(latestTimer);latestTimer=null;}
    }
}

function toggleRealtime(){
    realtimeMode=!realtimeMode;
    const btn=document.getElementById('btn-realtime');
    if(realtimeMode){
        btn.style.background='#e74c3c';btn.style.color='#fff';
        realtimeStart=Date.now();
        // 加载最近7天K线让指标充分预热
        const now=new Date();
        const fmt=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T'+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
        const sevenDaysAgo=new Date(now.getTime()-7*24*3600*1000);
        document.getElementById('sel-end').value=fmt(now);
        document.getElementById('sel-start').value=fmt(sevenDaysAgo);
        document.getElementById('date-range').value='';
        loadData();
        if(realtimeTimer)clearInterval(realtimeTimer);
        realtimeTimer=setInterval(()=>{if(realtimeMode)silentReload();},30000);
    }else{
        btn.style.background='#1e2a45';btn.style.color='#8892b0';
        if(realtimeTimer){clearInterval(realtimeTimer);realtimeTimer=null;}
    }
}

function silentReload(){
    const lookahead=document.getElementById('sel-lookahead').value;
    const start=document.getElementById('sel-start').value;
    const end=document.getElementById('sel-end').value;
    const dateRange=parseDateRange(document.getElementById('date-range'));
    let url='/api/backtest?style='+currentStyle+'&lookahead='+lookahead+'&_t='+Date.now();
    if(realtimeMode)url+='&trade_start='+realtimeStart;
    if(dateRange){url+='&start='+encodeURIComponent(dateRange.start);}
    else if(start){url+='&start='+start;}
    fetch(url).then(r=>r.json()).then(d=>{
        if(d.error)return;
        candles=d.candles||[];trades=d.trades||[];stats=d.stats||{};window._cdZones=d.sl_cooldown_zones||[];
        lastPrediction=d.prediction||null;
        renderChart(true);renderStats();renderTable();renderDistChart();
        updateNetPnl();
        const info=document.getElementById('tb-info');
        info.textContent=(realtimeMode?'🔴 ':'📡 ')+d.total_candles+'根K线 · '+stats.total_trades+'笔交易';
        if(d.date_range)info.textContent+=' · '+d.date_range.start+'~'+d.date_range.end;
        if(lastPrediction)info.textContent+=' · 📡 最新预测:'+(lastPrediction.direction==='bullish'?'📈':'📉')+lastPrediction.confidence+'%';
    }).catch(()=>{});
}

function setStyle(style){
    currentStyle=style;
    document.querySelectorAll('.st-btn').forEach(b=>{b.style.background='transparent';b.style.color='#525f7a'});
    const btn=document.getElementById(style==='short_term'?'bt-short':'bt-medium');
    btn.style.background='#667eea';btn.style.color='#fff';
    loadData();
}

// ---- 日期历史记录 ----
const DATE_HISTORY_KEY='cryptopulse_date_history';
function initDateHistory(){
    const input=document.getElementById('date-range');
    const dropdown=document.getElementById('date-history');
    if(!input||!dropdown)return;
    // 点击输入框切换下拉显示
    input.addEventListener('click',function(e){
        e.stopPropagation();
        const history=JSON.parse(localStorage.getItem(DATE_HISTORY_KEY)||'[]');
        if(!history.length){dropdown.style.display='none';return;}
        if(dropdown.style.display==='block'){dropdown.style.display='none';return;}
        const rect=this.getBoundingClientRect();
        dropdown.style.left=rect.left+'px';
        dropdown.style.top=(rect.bottom+2)+'px';
        dropdown.style.width=Math.max(rect.width,280)+'px';
        dropdown.innerHTML=history.map((item,i)=>{
            const isActive=item===this.value;
            return '<div class="dh-item" data-val="'+item.replace(/"/g,'&quot;')+'" style="padding:6px 10px;cursor:pointer;display:flex;justify-content:space-between;align-items:center'+(isActive?';background:#1e2a45':'')+'" onmouseover="this.style.background=\'#1e2a45\'" onmouseout="this.style.background=\'\'">'
                +'<span>'+(item.length>40?item.slice(0,40)+'...':item)+'</span>'
                +'<span style="font-size:9px;color:#525f7a">'+(i===0?'最近':'')+'</span>'
                +'</div>';
        }).join('')+'<div style="border-top:1px solid #1e2a45;padding:4px 10px"><span style="font-size:10px;color:#525f7a;cursor:pointer" id="dh-clear">清除历史记录</span></div>';
        dropdown.style.display='block';
    });
    // 点击其他地方关闭
    document.addEventListener('click',function(e){
        if(!dropdown.contains(e.target)&&e.target!==input){
            dropdown.style.display='none';
        }
    });
    // 委托点击
    dropdown.addEventListener('click',function(e){
        e.stopPropagation();
        const item=e.target.closest('.dh-item');
        if(item){selectDateHistory(item.dataset.val);}
        if(e.target.id==='dh-clear'){clearDateHistory();}
    });
}
function selectDateHistory(val){
    document.getElementById('date-range').value=val;
    document.getElementById('date-history').style.display='none';
    const btn=document.querySelector('.btn-r[onclick*="loadData"]');
    if(btn)btn.click();
}
function clearDateHistory(){
    localStorage.removeItem(DATE_HISTORY_KEY);
    document.getElementById('date-history').style.display='none';
}
function saveDateHistory(val){
    if(!val||val.length<5)return;
    let history=JSON.parse(localStorage.getItem(DATE_HISTORY_KEY)||'[]');
    history=history.filter(item=>item!==val);
    history.unshift(val);
    if(history.length>20)history=history.slice(0,20);
    localStorage.setItem(DATE_HISTORY_KEY,JSON.stringify(history));
}
