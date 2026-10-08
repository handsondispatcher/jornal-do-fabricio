"""Best-effort market snapshots; never infer a quote from a failed request."""
import datetime as dt, json, urllib.request, csv, io
from pathlib import Path
BASE=Path(__file__).resolve().parent

def request_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'JornalDoFabricio/1.0 (public market snapshot)','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=7) as r:
        return json.load(r)

def main():
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    out={'checked_at':now,'items':[]}
    specs=[('USD/BRL','USDBRL','Dólar comercial'),('EUR/BRL','EURBRL','Euro comercial')]
    try:
        data=request_json('https://economia.awesomeapi.com.br/json/last/USD-BRL,EUR-BRL')
        for symbol,key,label in specs:
            x=data.get(key,{})
            try:
                price=float(x['bid']);pct=float(x.get('pctChange',0))
                if price<=0:raise ValueError('invalid')
                out['items'].append({'symbol':symbol,'label':label,'value':f'R$ {price:.4f}'.replace('.',','),'change':pct,'source':'AwesomeAPI','asof':x.get('create_date',''),'status':'indicativo'})
            except (ValueError,KeyError,TypeError):pass
    except Exception as exc:
        print('Câmbio indisponível:',type(exc).__name__)
    # Fechamentos históricos de índices dos EUA, quando disponíveis via Stooq.
    for symbol, ticker in [('S&P 500','^spx'),('NASDAQ','^ndq')]:
        try:
            url='https://stooq.com/q/d/l/?s='+ticker+'&i=d&d1='+(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=12)).strftime('%Y%m%d')+'&d2='+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d')
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=7) as r: raw=r.read(120000).decode('utf-8-sig')
            rows=[row for row in csv.DictReader(io.StringIO(raw)) if row.get('Close') and row.get('Date')]
            if rows:
                latest=rows[-1];price=float(latest['Close']);previous=float(rows[-2]['Close']) if len(rows)>1 else None
                if price>0:
                    out['items'].append({'symbol':symbol,'label':symbol,'value':f'{price:,.2f}'.replace(',','X').replace('.',',').replace('X','.'),'change':round((price/previous-1)*100,2) if previous else None,'source':'Stooq','asof':latest['Date'],'status':'último fechamento'})
        except Exception as exc:print('Fechamento não disponível',symbol,type(exc).__name__)
    # Índices sem fonte confirmada não são preenchidos artificialmente.
    for symbol,label in [('IBOV','Ibovespa · B3'),('IFIX','Fundos imobiliários'),('S&P 500','S&P 500'),('NASDAQ','Nasdaq')]:
        if any(x['symbol']==symbol for x in out['items']):continue
        out['items'].append({'symbol':symbol,'label':label,'value':None,'change':None,'source':None,'asof':None,'status':'aguardando fonte de mercado'})
    (BASE/'mercados.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Mercados:',sum(x['value'] is not None for x in out['items']),'cotações obtidas')
if __name__=='__main__':main()
