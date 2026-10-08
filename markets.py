"""Snapshots financeiros informativos para publicação estática.

Não é feed de bolsa em tempo real. Cada ponto possui fonte e período da
variação; em falhas de rede preserva o último snapshot, marcado como antigo.
Não fabrica variações, preços ou fechamentos.
"""
from __future__ import annotations
import csv
import datetime as dt
import io
import json
import math
from pathlib import Path
import urllib.parse as up
import urllib.request as ur
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
DEST = BASE / 'mercados.json'
UTC = dt.timezone.utc

def number(raw):
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise ValueError('preço inválido')
    return value

def percentage(raw):
    if raw is None or raw == '':return None
    v = float(raw)
    if not math.isfinite(v) or abs(v)>1000:raise ValueError('variação inválida')
    return round(v, 2)

def br_number(value, digits=2):
    return f'{value:,.{digits}f}'.replace(',', '#').replace('.', ',').replace('#', '.')

def item(symbol,label,price,prefix,change,source,asof,status,period=None,digits=2):
    price = number(price)
    return {'symbol':symbol,'label':label,'value':prefix+br_number(price,digits),
            'price':price,'currency':prefix.strip(),'change':percentage(change),
            'change_period':period, 'source':source,'asof':str(asof),
            'status':status,'stale':False}

def get_json(url,timeout=8):
    req=ur.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; JornalDoFabricio/4.14; financial-snapshot)','Accept':'application/json'})
    with ur.urlopen(req,timeout=timeout) as r:return json.load(r)

def get_text(url,timeout=8):
    req=ur.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'text/csv,text/plain'})
    with ur.urlopen(req,timeout=timeout) as r:return r.read(150_000).decode('utf-8-sig')

def fetch_fx():
    data=get_json('https://economia.awesomeapi.com.br/json/last/USD-BRL,EUR-BRL')
    records=[]
    for symbol,key,label in [('USD/BRL','USDBRL','Dólar comercial'),('EUR/BRL','EURBRL','Euro comercial')]:
        row=data.get(key) or {}
        try:
            price=number(row['bid'])
            # pctChange significa variação divulgada pela própria API, sem
            # reinterpretá-la como variação oficial do dia ou PTAX.
            change=percentage(row.get('pctChange'))
            records.append(item(symbol,label,price,'R$ ',change,'AwesomeAPI',row.get('create_date') or row.get('timestamp') or '','cotação indicativa', 'variação informada pela fonte',4))
        except (KeyError,TypeError,ValueError):continue
    return records

def fetch_btc_stats(now):
    """Coinbase Exchange fornece open e last da mesma janela de 24h."""
    data=get_json('https://api.exchange.coinbase.com/products/BTC-USD/stats')
    price=number(data['last']); opening=number(data['open'])
    return item('BTC/USD','Bitcoin',price,'US$ ',(price/opening-1)*100,'Coinbase Exchange',now.isoformat(timespec='seconds'),'cotação 24h/7','24h')

def fetch_btc_gecko(now):
    url='https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true&include_last_updated_at=true'
    data=get_json(url)['bitcoin']
    stamp=dt.datetime.fromtimestamp(int(data['last_updated_at']),UTC).isoformat(timespec='seconds')
    return item('BTC/USD','Bitcoin',data['usd'],'US$ ',data['usd_24h_change'],'CoinGecko',stamp,'cotação 24h/7','24h')

def fetch_btc_spot(now):
    data=get_json('https://api.coinbase.com/v2/prices/BTC-USD/spot')
    # Se as fontes de variação falharem, mostrar apenas o preço, SEM cor.
    return item('BTC/USD','Bitcoin',data['data']['amount'],'US$ ',None,'Coinbase Spot',now.isoformat(timespec='seconds'),'spot sem variação verificada')

YAHOO={
    'IBOV':('^BVSP','Ibovespa · B3','',ZoneInfo('America/Sao_Paulo')),
    'BRENT':('BZ=F','Petróleo Brent (futuro)','US$ ',ZoneInfo('America/New_York')),
    'S&P 500':('^GSPC','S&P 500','',ZoneInfo('America/New_York')),
    'NASDAQ':('^IXIC','Nasdaq Composite','',ZoneInfo('America/New_York')),
}
STOOQ={'IBOV':'^bvsp','S&P 500':'^spx','NASDAQ':'^ndq'}

def yahoo_daily(symbol, now):
    ticker,label,prefix,zone=YAHOO[symbol]
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+up.quote(ticker,safe='')+'?interval=1d&range=14d'
    results=get_json(url)['chart']['result']
    if not results:raise ValueError('sem série')
    chart=results[0]
    closes=(chart.get('indicators',{}).get('quote') or [{}])[0].get('close') or []
    times=chart.get('timestamp') or []
    points=[]
    for stamp,price in zip(times,closes):
        try:points.append((dt.datetime.fromtimestamp(int(stamp),UTC),number(price)))
        except (ValueError,TypeError,OverflowError):continue
    if not points:raise ValueError('sem preço')
    asof,price=points[-1]
    prev=points[-2][1] if len(points)>1 else None
    change=(price/prev-1)*100 if prev else None
    meta=chart.get('meta') or {}
    # Meta de fechamento (Yahoo); o candle diário do pregão corrente pode
    # estar incompleto. Nunca declarar como "ao vivo".
    status='último ponto diário (pode ser parcial)'
    if asof.astimezone(zone).date()<now.astimezone(zone).date():status='último fechamento disponível'
    return item(symbol,label,price,prefix,change,'Yahoo Finance (indicativo)',asof.isoformat(timespec='seconds'),status,'comparação entre pontos diários')

def stooq_daily(symbol,now):
    ticker=STOOQ[symbol]
    date1=(now-dt.timedelta(days=25)).strftime('%Y%m%d')
    date2=now.strftime('%Y%m%d')
    raw=get_text('https://stooq.com/q/d/l/?'+up.urlencode({'s':ticker,'i':'d','d1':date1,'d2':date2}))
    rows=[]
    for row in csv.DictReader(io.StringIO(raw)):
        try:rows.append((row['Date'],number(row['Close'])))
        except (ValueError,KeyError,TypeError):continue
    if not rows:raise ValueError('sem preços')
    label=YAHOO[symbol][1]
    price=rows[-1][1];prev=rows[-2][1] if len(rows)>1 else None
    change=(price/prev-1)*100 if prev else None
    return item(symbol,label,price,'',change,'Stooq (fechamento diário)',rows[-1][0],'último fechamento disponível','dia anterior')

def collect_snapshot(now=None, previous=None):
    """Permite testes offline com funções de rede injetadas."""
    now=now or dt.datetime.now(UTC)
    previous=previous or {}
    if now.tzinfo is None:now=now.replace(tzinfo=UTC)
    result={'checked_at':now.isoformat(timespec='seconds'),'items':[], 'version':2}
    logs=[]
    def try_call(label,fn):
        try:return fn()
        except (ValueError,KeyError,TypeError,IndexError,OSError,TimeoutError) as exc:
            logs.append(label+': '+type(exc).__name__)
            return None
        except Exception as exc:
            logs.append(label+': '+type(exc).__name__)
            return None
    for quote in try_call('Câmbio',fetch_fx) or []:result['items'].append(quote)
    for sym in YAHOO:
        quote=try_call(sym+' Yahoo',lambda s=sym:yahoo_daily(s,now))
        if quote is None and sym in STOOQ:
            quote=try_call(sym+' Stooq',lambda s=sym:stooq_daily(s,now))
        if quote:result['items'].append(quote)
    btc=try_call('Bitcoin Coinbase 24h',lambda:fetch_btc_stats(now))
    if btc is None:btc=try_call('Bitcoin CoinGecko 24h',lambda:fetch_btc_gecko(now))
    if btc is None:btc=try_call('Bitcoin Spot',lambda:fetch_btc_spot(now))
    if btc:result['items'].append(btc)
    old={x['symbol']:x for x in previous.get('items',[]) if isinstance(x,dict) and x.get('value') and x.get('symbol')}
    received={x['symbol'] for x in result['items']}
    for sym,prior in old.items():
        if sym not in received:
            record=dict(prior);record['stale']=True;record['status']='último valor disponível — sem atualização da fonte'
            result['items'].append(record)
    for sym,label in [('USD/BRL','Dólar comercial'),('EUR/BRL','Euro comercial'),('IBOV','Ibovespa · B3'),('BRENT','Petróleo Brent'),('S&P 500','S&P 500'),('NASDAQ','Nasdaq'),('BTC/USD','Bitcoin')]:
        if sym not in {x['symbol'] for x in result['items']}:
            result['items'].append({'symbol':sym,'label':label,'value':None,'change':None,'source':None,'asof':None,'status':'fonte indisponível','stale':False})
    order={'USD/BRL':0,'EUR/BRL':1,'IBOV':2,'BRENT':3,'S&P 500':4,'NASDAQ':5,'BTC/USD':6}
    result['items'].sort(key=lambda r:order.get(r['symbol'],100))
    result['errors']=logs
    return result

def main():
    try:previous=json.loads(DEST.read_text(encoding='utf-8'))
    except (OSError,ValueError):previous={}
    result=collect_snapshot(previous=previous)
    DEST.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Mercados:',sum(bool(x.get('value')) for x in result['items']),'de 7 séries com valor disponível;',len(result['errors']),'consultas sem resposta.')

if __name__=='__main__':main()
