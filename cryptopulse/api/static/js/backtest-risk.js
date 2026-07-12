let btRiskStatus = null;
function fetchRiskStatus() {
    fetch('/api/risk/status').then(r => r.json()).then(d => {
        if (d.error) return;
        btRiskStatus = d;
        const el = document.getElementById('bt-risk-indicator');
        const txt = document.getElementById('bt-risk-text');
        if (d.in_sl_cooldown) {
            el.style.display = 'inline';
            el.style.background = 'rgba(255,152,0,0.2)';
            el.style.border = '1px solid #ff9800';
            el.style.color = '#ff9800';
            txt.textContent = d.sl_cooldown_display + '冷却';
        } else if (d.sl_triggered) {
            el.style.display = 'inline';
            el.style.background = 'rgba(76,175,80,0.15)';
            el.style.border = '1px solid #4caf50';
            el.style.color = '#4caf50';
            txt.textContent = '风控正常';
        } else {
            el.style.display = 'none';
        }
    }).catch(() => {});
}
function showRiskDetail() {
    if (!btRiskStatus) { fetchRiskStatus(); return; }
    const d = btRiskStatus;
    let html = '<div style="font-size:12px;line-height:1.8">';
    if (d.in_sl_cooldown) {
        html += '<div style="color:#ff9800;font-weight:600;font-size:14px">⚠️ 止损冷却中</div>';
        html += '<div style="color:#525f7a">剩余 ' + d.sl_cooldown_display + '</div>';
    } else {
        html += '<div style="color:#4caf50;font-weight:600;font-size:14px">✅ 风控正常</div>';
    }
    if (d.last_sl_time_str) {
        html += '<div style="color:#525f7a;margin-top:4px">上次止损: ' + d.last_sl_time_str + '</div>';
        html += '<div style="color:#8892b0">原因: ' + (d.sl_reason || '未知') + '</div>';
    }
    html += '<div style="color:#525f7a;margin-top:4px;font-size:11px">🔄 冷却期5分钟，期间不能开新仓，原有持仓平仓/止盈正常</div>';
    html += '<div style="margin-top:8px"><button onclick="document.getElementById(\'dl-overlay\').style.display=\'none\'" style="background:#1e2a45;border:none;color:#8892b0;padding:4px 14px;border-radius:4px;cursor:pointer;font-size:11px">关闭</button></div>';
    html += '</div>';
    document.getElementById('dl-trade').style.display = 'none';
    document.getElementById('dl-kdata').style.display = 'none';
    document.getElementById('dl-reason').style.display = 'block';
    document.getElementById('dl-reason').innerHTML = html;
    document.getElementById('dl-overlay').style.display = 'block';
}
function renderRiskPanel() {
    const el = document.getElementById('risk-panel');
    // 统计被风控阻止的信号
    const riskBlockedCandles = candles.filter(c => c.s && c.s.risk_blocked);
    const totalSignals = candles.filter(c => c.s && c.s.direction !== 'neutral').length;
    // 按原因分类
    const byReason = {};
    riskBlockedCandles.forEach(c => {
        const r = c.s.risk_reason || '未知';
        if (!byReason[r]) byReason[r] = [];
        byReason[r].push(c);
    });
    const maxCount = Math.max(...Object.values(byReason).map(a => a.length), 1);

    let html = '<div style="padding:10px">';
    // 总览卡片
    html += '<div style="background:#131a2b;border-radius:8px;padding:14px;margin-bottom:10px">';
    html += '<div style="font-size:13px;font-weight:600;color:#e8edf5;margin-bottom:8px">风控阻止统计</div>';
    html += '<div style="display:flex;gap:10px;text-align:center">';
    html += '<div style="flex:1;background:#0b0e17;border-radius:6px;padding:10px"><div style="font-size:22px;font-weight:700;color:#ff9800">' + riskBlockedCandles.length + '</div><div style="font-size:10px;color:#525f7a;margin-top:2px">被阻止</div></div>';
    html += '<div style="flex:1;background:#0b0e17;border-radius:6px;padding:10px"><div style="font-size:22px;font-weight:700;color:#667eea">' + totalSignals + '</div><div style="font-size:10px;color:#525f7a;margin-top:2px">总信号</div></div>';
    html += '<div style="flex:1;background:#0b0e17;border-radius:6px;padding:10px"><div style="font-size:22px;font-weight:700;color:' + (totalSignals > 0 ? '#e8edf5' : '#525f7a') + '">' + (totalSignals > 0 ? (riskBlockedCandles.length/totalSignals*100).toFixed(1) : '0') + '%</div><div style="font-size:10px;color:#525f7a;margin-top:2px">阻止率</div></div>';
    html += '</div></div>';

    // 各原因分布（可点击高亮）
    html += '<div style="background:#131a2b;border-radius:8px;padding:14px;margin-bottom:10px">';
    html += '<div style="font-size:13px;font-weight:600;color:#e8edf5;margin-bottom:8px">风控原因分布</div>';
    if (riskBlockedCandles.length === 0) {
        html += '<div style="color:#525f7a;font-size:11px;padding:10px 0;text-align:center">暂无风控阻止</div>';
    } else {
        Object.keys(byReason).sort((a,b) => byReason[b].length - byReason[a].length).forEach(r => {
            const cnt = byReason[r].length;
            const pct = (cnt / riskBlockedCandles.length * 100).toFixed(1);
            const w = Math.max(cnt / maxCount * 100, 5);
            const selected = highlightFilter && highlightFilter.type === 'risk' && highlightFilter.value === r;
            const shortLabel = r.indexOf('止损冷却') >= 0 ? '🛑 止损冷却' : (r.indexOf('TP1利润') >= 0 ? '💰 利润不足' : r);
            html += '<div class="dist-bar-wrap" style="cursor:pointer;opacity:' + (highlightFilter && !selected ? 0.4 : 1) + '" onclick="setRiskHighlight(\'' + r.replace(/'/g, "\\'") + '\')">';
            html += '<span class="dist-label" style="width:80px;font-size:10px">' + shortLabel + '</span>';
            html += '<div class="dist-bar-bg"><div class="dist-bar-fill" style="width:' + w + '%;background:#ff9800">' + cnt + '</div></div>';
            html += '<span style="font-size:10px;color:#ff9800;width:36px;text-align:left">' + pct + '%</span></div>';
        });
        html += '<div style="margin-top:4px;font-size:9px;color:#525f7a">点击可高亮K线图中对应风控信号</div>';
    }
    html += '</div>';

    // 风控规则说明
    html += '<div style="background:#131a2b;border-radius:8px;padding:14px">';
    html += '<div style="font-size:13px;font-weight:600;color:#e8edf5;margin-bottom:8px">风控规则说明</div>';
    html += '<div style="font-size:11px;line-height:1.8;color:#8892b0">';
    html += '<div>1️⃣ <b>止损冷却</b>：止损触发后暂停交易5分钟，期间不开新仓</div>';
    html += '<div>2️⃣ <b>保本检查</b>：TP1利润 > 双边手续费才进场（当前费率 ' + (Number(document.getElementById('pos-fee').value) * 100).toFixed(2) + '%，需 ≥ ' + (Number(document.getElementById('pos-fee').value) * 2 * 100).toFixed(2) + '%）</div>';
    html += '</div></div>';

    if (highlightFilter && highlightFilter.type === 'risk') {
        html += '<div style="margin-top:6px"><button onclick="clearHighlight()" style="padding:3px 10px;border:none;border-radius:4px;font-size:10px;background:#667eea;color:#fff;cursor:pointer">清除高亮</button></div>';
    }
    html += '</div>';
    el.innerHTML = html;
}

function setRiskHighlight(reason) {
    if (highlightFilter && highlightFilter.type === 'risk' && highlightFilter.value === reason) {
        clearHighlight();
        return;
    }
    highlightFilter = { type: 'risk', value: reason };
    renderChart(true);
    renderRiskPanel();
}

initChart();
setTimeout(fetchRiskStatus, 500);
setInterval(fetchRiskStatus, 10000);

// 检查是否有待执行的回测参数（页面刷新后自动开始）
(function(){
    const saved=sessionStorage.getItem('bk_params');
    if(saved){
        sessionStorage.removeItem('bk_params');
        try{
            const p=JSON.parse(saved);
            if(p.dateRange)document.getElementById('date-range').value=p.dateRange;
            if(p.start)document.getElementById('sel-start').value=p.start;
            if(p.end)document.getElementById('sel-end').value=p.end;
            if(p.lookahead)document.getElementById('sel-lookahead').value=p.lookahead;
            setTimeout(loadData,100);
        }catch(e){}
    }
})();