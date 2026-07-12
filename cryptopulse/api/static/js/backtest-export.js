function exportCSV(){
    // 直接从前端已加载的数据生成CSV（不请求后端，解决卡死问题）
    if(!trades||!trades.length){alert('没有交易数据可导出，请先运行回测');return;}
    const cap=document.getElementById('pos-capital').value||1000;
    const lev=document.getElementById('pos-leverage').value||1;
    const fee=parseFloat(document.getElementById('pos-fee').value)||0.0005;
    const lookahead=document.getElementById('sel-lookahead').value||5;
    const intervalLabel=currentStyle==='short_term'?'1m':'4H';
    const timeoutMinutes=currentStyle==='short_term'?lookahead*1:lookahead*240;
    const timeoutLabel=currentStyle==='short_term'?lookahead+'分钟':(lookahead*4+'小时');
    const ft=getFilteredTrades(trades);
    // ---- 回测结果汇总 ----
    const slCount=trades.filter(t=>t.exit_reason==='止损').length;
    const tpCount=trades.filter(t=>t.exit_reason==='止盈').length;
    const toCount=trades.filter(t=>t.exit_reason==='超时'||t.exit_reason==='时间到').length;
    const totalPnl=stats?stats.total_pnl_pct:(trades.reduce((s,t)=>s+t.pnl_pct,0));
    const winRate=stats?stats.win_rate:((trades.filter(t=>t.pnl_pct>0).length/trades.length*100).toFixed(1));
    const acc=stats?stats.accuracy:((trades.filter(t=>t.correct).length/trades.length*100).toFixed(1));
    let csv='【回测结果汇总】\n';
    csv+='交易笔数,'+trades.length+'\n正确,'+trades.filter(t=>t.correct).length+','+acc+'%\n错误,'+trades.filter(t=>!t.correct).length+','+(100-parseFloat(acc)).toFixed(1)+'%\n';
    csv+='准确率,'+acc+'%\n总毛利,'+(totalPnl>=0?'+':'')+parseFloat(totalPnl).toFixed(2)+'%\n总手续费,'+(trades.length*fee*2*100).toFixed(2)+'%\n净利,'+((totalPnl||0)-trades.length*fee*2*100).toFixed(2)+'%\n';
    csv+='胜率,'+winRate+'%\n盈亏比,'+(stats?stats.profit_factor:'--')+'\n平均盈,'+(stats?stats.avg_win+'%':'--')+'\n平均亏,'+(stats?stats.avg_loss+'%':'--')+'\n';
    csv+='止损,'+slCount+'笔('+(trades.length?(slCount/trades.length*100).toFixed(1):'0')+'%)\n止盈,'+tpCount+'笔('+(trades.length?(tpCount/trades.length*100).toFixed(1):'0')+'%)\n超时,'+toCount+'笔('+(trades.length?(toCount/trades.length*100).toFixed(1):'0')+'%)\n';
    csv+='【仓位参数】\n本金,'+cap+' USDT\n杠杆,'+parseInt(lev)+'x\n费率,'+(fee*100).toFixed(2)+'%\n每笔手续费,'+(fee*2*100).toFixed(3)+'%\n总手续费金额,'+(trades.length*fee*2*cap*lev/100).toFixed(1)+' USDT\n周期,'+intervalLabel+'\n验证值,'+lookahead+'根K线\n超时时间,'+timeoutLabel+'\n\n';
    // 超时细分
    const toProfit=trades.filter(t=>(t.exit_reason==='超时'||t.exit_reason==='时间到')&&t.pnl_pct>0).length;
    const toLoss=toCount-toProfit;
    csv+='超时盈利,'+toProfit+'笔,'+(toCount?((toProfit/toCount*100).toFixed(1)+'%'):'0%')+'\n超时亏损,'+toLoss+'笔,'+(toCount?((toLoss/toCount*100).toFixed(1)+'%'):'0%')+'\n\n';
    const totalSig=candles.filter(c=>c.s).length;
    const bullCount=candles.filter(c=>c.s&&c.s.direction==='bullish').length;
    const bearCount=candles.filter(c=>c.s&&c.s.direction==='bearish').length;
    const neuCount=candles.filter(c=>c.s&&c.s.direction==='neutral').length;
    csv+='【信号明细汇总】\n总信号数,'+totalSig+'\n做多,'+bullCount+'\n做空,'+bearCount+'\n观望,'+neuCount+'\n';
    csv+='做多占比,'+(totalSig?(bullCount/totalSig*100).toFixed(1):'0')+'%\n做空占比,'+(totalSig?(bearCount/totalSig*100).toFixed(1):'0')+'%\n观望占比,'+(totalSig?(neuCount/totalSig*100).toFixed(1):'0')+'%\n\n';
    // 下载：使用HTML表格格式（兼容Excel，支持列宽），文件名精确到秒
    const now=new Date();
    const ts=now.getFullYear()
        +String(now.getMonth()+1).padStart(2,'0')+String(now.getDate()).padStart(2,'0')+'_'
        +String(now.getHours()).padStart(2,'0')+String(now.getMinutes()).padStart(2,'0')+String(now.getSeconds()).padStart(2,'0');
    // 信号明细CSV
    csv+='#,time,price,open,high,low,volume,direction,score,confidence,reason,entry_price,sl_price,exit_price,exit_reason,correct,pnl_pct,保本,风控原因\n';
    const tradeMap={};
    trades.forEach(t=>{tradeMap[t.timestamp]=t;});
    let sigIdx=0;
    candles.forEach(c=>{
        if(!c.s)return;
        sigIdx++;
        const t=c.s;
        const tr=tradeMap[c.t];
        const timeStr=new Date(c.t).toISOString().slice(0,19).replace('T',' ');
        const reason=(t.reason||'').replace(/,/g,';');
        const row=[
            sigIdx,timeStr,c.c.toFixed(1),c.o.toFixed(1),c.h.toFixed(1),c.l.toFixed(1),c.v,
            t.direction,t.score,t.confidence,reason,
            tr?tr.entry_price:'',tr?tr.sl_price:'',tr?tr.exit_price:'',
            tr?tr.exit_reason:'',tr?(tr.correct?'Y':'N'):'',
            tr?((tr.pnl_pct>=0?'+':'')+tr.pnl_pct+'%'):'',
            tr?(Math.abs(tr.pnl_pct)>=fee*2*100?'已触发':'未触发'):'',
            t.risk_reason||''
        ];
        csv+=row.join(',')+'\n';
    });
    // 下载CSV
    const blob=new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'});
    const a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download='backtest_'+currentStyle+'_'+ts+'.csv';
    a.click();
    URL.revokeObjectURL(a.href);
}
