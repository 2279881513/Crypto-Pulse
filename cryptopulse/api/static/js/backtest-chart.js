function initChart() {
    const wrap = document.getElementById('chart-wrap');
    chart = LightweightCharts.createChart(wrap, {
        layout: {background:{type:'solid',color:'#0b0e17'},textColor:'#525f7a',fontSize:10,fontFamily:'Courier New, monospace'},
        grid: {vertLines:{color:'#131a2b'},horzLines:{color:'#131a2b'}},
        crosshair: {mode:LightweightCharts.CrosshairMode.Normal,vertLine:{color:'#2a3a55',width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:'#1e2a45'},horzLine:{color:'#2a3a55',width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:'#1e2a45'}},
        timeScale: {borderColor:'#1a2340',timeVisible:true,secondsVisible:false,tickMarkFormatter:t=>{const d=new Date(t*1000);return String(d.getUTCHours()).padStart(2,'0')+':'+String(d.getUTCMinutes()).padStart(2,'0')}},
        rightPriceScale: {borderColor:'#1a2340'},
        handleScroll: {vertTouchDrag:false},
    });
    candleSeries = chart.addCandlestickSeries({upColor:'#2ecc71',downColor:'#e74c3c',borderDownColor:'#e74c3c',borderUpColor:'#2ecc71',wickDownColor:'#e74c3c',wickUpColor:'#2ecc71'});
    volumeSeries = chart.addHistogramSeries({color:'#1a2340',priceFormat:{type:'volume'},priceScaleId:''});
    predSeries = chart.addCandlestickSeries({
        upColor:'rgba(102,126,234,0.4)',downColor:'rgba(118,75,162,0.4)',
        borderUpColor:'#667eea',borderDownColor:'#764ba2',
        wickUpColor:'#667eea',wickDownColor:'#764ba2',
    });
    histPredSeries = chart.addCandlestickSeries({
        upColor:'rgba(46,204,113,0.25)',downColor:'rgba(231,76,60,0.25)',
        borderUpColor:'rgba(46,204,113,0.5)',borderDownColor:'rgba(231,76,60,0.5)',
        wickUpColor:'rgba(46,204,113,0.25)',wickDownColor:'rgba(231,76,60,0.25)',
        priceLineVisible:false,
    });
    cdZoneSeries = chart.addHistogramSeries({
        color:'rgba(255,152,0,0.35)',priceFormat:{type:'volume'},
        priceScaleId:'',
    });
    chart.priceScale('').applyOptions({scaleMargins:{top:0.8,bottom:0}});
    new ResizeObserver(()=>{if(chart)chart.resize(wrap.clientWidth,wrap.clientHeight)}).observe(wrap);
    chart.subscribeCrosshairMove(param=>{
        const tip=document.getElementById('tip');
        if(!param.time||!param.point){tip.style.display='none';clearPlines();return}
        const c=candles.find(x=>Math.floor(x.t/1000)===param.time);
        if(!c){tip.style.display='none';clearPlines();return}
        const t=trades.find(x=>x.timestamp===c.t);
        clearPlines();
        if(t){
            if(t.sl_price)plineRefs.push(candleSeries.createPriceLine({price:t.sl_price,color:'#e74c3c',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'止损'}));
            if(t.tp_price)plineRefs.push(candleSeries.createPriceLine({price:t.tp_price,color:'#2ecc71',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'止盈'}));
            if(t.entry_price)plineRefs.push(candleSeries.createPriceLine({price:t.entry_price,color:'#f1c40f',lineWidth:1,lineStyle:0,axisLabelVisible:true,title:'入场'}));
            // 查找出场K线位置并标记紫色水平线
            const entryIdx=candles.findIndex(x=>x.t===c.t);
            if(entryIdx>=0){
                const isBull=t.direction==='bullish';
                for(let ei=entryIdx+1;ei<candles.length;ei++){
                    const ec=candles[ei];
                    const matchedTP=isBull?(ec.h>=t.tp_price):(ec.l<=t.tp_price);
                    const matchedSL=isBull?(ec.l<=t.sl_price):(ec.h>=t.sl_price);
                    if(t.exit_reason==='止盈'&&matchedTP){plineRefs.push(candleSeries.createPriceLine({price:t.exit_price,color:'#7c4dff',lineWidth:1,lineStyle:0,axisLabelVisible:true,title:'✨ 止盈出场'}));break;}
                    if(t.exit_reason==='止损'&&matchedSL){plineRefs.push(candleSeries.createPriceLine({price:t.exit_price,color:'#7c4dff',lineWidth:1,lineStyle:0,axisLabelVisible:true,title:'🛑 止损出场'}));break;}
                    if(t.exit_reason==='超时'||t.exit_reason==='时间到'){
                        if(ei-entryIdx>=5){plineRefs.push(candleSeries.createPriceLine({price:t.exit_price,color:'#7c4dff',lineWidth:1,lineStyle:0,axisLabelVisible:true,title:'⏱️ 超时出场'}));break;}
                    }
                }
            }
        }
        const ts=param.time*1000;
        let html='<div class="tip-row"><span class="tip-l">时间</span><span class="tip-v">'+new Date(ts).toISOString().slice(0,16).replace('T',' ')+'</span></div>'
            +'<div class="tip-row"><span class="tip-l">O/C</span><span class="tip-v">'+c.o.toFixed(1)+' / '+c.c.toFixed(1)+'</span></div>'
            +'<div class="tip-row"><span class="tip-l">H/L</span><span class="tip-v">'+c.h.toFixed(1)+' / '+c.l.toFixed(1)+'</span></div>';
        if(c.s){const d=c.s.direction==='bullish'?'📈 多':(c.s.direction==='bearish'?'📉 空':'⏸️');html+='<div class="tip-row"><span class="tip-l">信号</span><span class="tip-v" style="color:'+(c.s.direction==='bullish'?'#2ecc71':'#e74c3c')+'">'+d+'</span></div>'
            +'<div class="tip-row"><span class="tip-l">评分</span><span class="tip-v">'+Math.abs(c.s.score)+' / '+c.s.confidence+'%</span></div>'
            +(c.s.reason?'<div class="tip-row"><span class="tip-l">原因</span><span class="tip-v" style="color:#8892b0;font-size:10px">'+c.s.reason+'</span></div>':'')
            +(c.s.risk_blocked?'<div class="tip-row"><span class="tip-l" style="color:#ff9800">⚠️ 风控</span><span class="tip-v" style="color:#ff9800;font-size:10px">'+c.s.risk_reason+'</span></div>':'')}
        if(t){var dp=t.direction==='bullish';var pnl$=t.pnl_pct*Number(document.getElementById('pos-capital').value||1000)*Number(document.getElementById('pos-leverage').value||1)/100;
        var isFeeFiltered=document.getElementById('chk-fee-filter').checked && !getFilteredTrades(trades).some(tr=>tr.timestamp===c.t);
        var a=[];a.push('<div class="tip-row"><span class="tip-l">方向</span><span class="tip-v" style="color:'+(dp?'#2ecc71':'#e74c3c')+'">'+(dp?'📈 多':'📉 空')+'</span></div>');a.push('<div class="tip-row"><span class="tip-l">入场</span><span class="tip-v">'+t.entry_price+'</span></div>');if(t.sl_price){a.push('<div class="tip-row"><span class="tip-l" style="color:#e74c3c">止损</span><span class="tip-v" style="color:#e74c3c">'+t.sl_price+' ('+_fPct(t.sl_price,t.entry_price)+')</span></div>')}a.push('<div class="tip-row"><span class="tip-l">出场</span><span class="tip-v">'+t.exit_price+'</span></div>');var e=t.exit_reason||'';var ic=e==='止损'?'🛑':e==='超时'?'⏱️':'';a.push('<div class="tip-row"><span class="tip-l">离场</span><span class="tip-v" style="font-size:10px;color:#8892b0">'+ic+e+'</span></div>');if(isFeeFiltered){a.push('<div class="tip-row"><span class="tip-l">保本</span><span class="tip-v" style="font-size:10px;color:#525f7a">未触发</span></div>')}a.push('<div class="tip-row"><span class="tip-l">结果</span><span class="tip-v" style="color:'+(t.correct?'#2ecc71':'#e74c3c')+'">'+(t.correct?'✅':'❌')+'</span></div>');a.push('<div class="tip-row"><span class="tip-l">盈亏</span><span class="tip-v" style="color:'+(t.pnl_pct>=0?'#2ecc71':'#e74c3c')+'">'+(t.pnl_pct>=0?'+':'')+t.pnl_pct+'% $'+(pnl$>=0?'+':'')+pnl$.toFixed(2)+'</span></div>');html+=a.join('')}
        tip.innerHTML=html;
        const x=param.point.x,y=param.point.y,wr=document.getElementById('chart-wrap').getBoundingClientRect();
        tip.style.left=(x+15>wr.right?x-160:x+15)+'px';tip.style.top=(y-10<wr.top?y+20:y-10)+'px';tip.style.display='block'
    });
    initDates();

    // 右键菜单
    document.getElementById('chart-wrap').addEventListener('contextmenu',e=>{
        e.preventDefault();
        document.getElementById('ctx-clear-hl').style.display=highlightFilter?'block':'none';
        const menu=document.getElementById('ctx-menu');
        menu.style.display='block';
        menu.style.left=Math.min(e.clientX,window.innerWidth-160)+'px';
        menu.style.top=Math.min(e.clientY,window.innerHeight-300)+'px';
    });
    document.addEventListener('click',()=>{document.getElementById('ctx-menu').style.display='none'});
}

function ctxAction(action){
    document.getElementById('ctx-menu').style.display='none';
    switch(action){
        case 'zoomIn':chart.timeScale().zoomOut();break;
        case 'zoomOut':chart.timeScale().zoomIn();break;
        case 'reset':chart.timeScale().fitContent();break;
        case 'togglePred':toggleHistPred();break;
        case 'clearHighlight':clearHighlight();break;
        case 'exportCsv':exportCSV();break;
    }
}
