
let chart, candleSeries, volumeSeries, predSeries, histPredSeries, cdZoneSeries;
let candles = [], trades = [], stats = null, allSignals = [];
let currentStyle = 'short_term';
let loadReqId = 0;
let showHistPred = false;
let lastPrediction = null;
let latestMode = false;
let latestTimer = null;
let realtimeMode = false;
let realtimeStart = 0;
let realtimeTimer = null;
let highlightFilter = null;
let loadAbort = null; // 取消上一次回测请求
let progTimer = null; // 进度条定时器
let loadCount = 0; // 回测次数统计

// 加载保存的仓位设置
(function(){
    try{
        const s=JSON.parse(localStorage.getItem('cryptopulse_settings')||'{}');
        if(s.capital)document.getElementById('pos-capital').value=s.capital;
        if(s.leverage)document.getElementById('pos-leverage').value=s.leverage;
        if(s.feeRate)document.getElementById('pos-fee').value=s.feeRate;
    }catch(e){}
})();

var plineRefs=[];function clearPlines(){plineRefs.forEach(p=>{try{candleSeries.removePriceLine(p)}catch(e){}});plineRefs=[];}
var _fPct=function(a,b){try{var r=((Number(a)/Number(b))-1)*100;return isNaN(r)?'':(r>=0?'+':'')+r.toFixed(2)+'%'}catch(e){return''}};
