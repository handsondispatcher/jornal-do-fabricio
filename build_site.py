import csv, datetime as dt, html, io, json, re, shutil, urllib.parse, urllib.request, concurrent.futures, sqlite3, time
from pathlib import Path
import engine
import source_selector
BASE=Path(__file__).parent

def e(s): return html.escape(str(s or ''),quote=True)

def summary_text(article):
    """Exibe somente informação disponível e substantiva, nunca texto de preenchimento."""
    title=re.sub(r'\s+', ' ', article['title']).strip()
    raw=re.sub(r'\s+', ' ', article.get('summary','')).strip()
    source=article.get('source','')
    if raw.casefold().startswith(title.casefold()):raw=raw[len(title):].lstrip(' -–—:|')
    if source and raw.casefold() in (source.casefold(), ''):raw=''
    if raw.casefold() in title.casefold() or english_title(raw):raw=''
    return raw[:650].rstrip(' ,;') if len(raw)>=40 else ''

# Complementa resumos RSS com a descrição editorial publicada na página da fonte.
# Não reproduz reportagens integrais nem inventa informações.
def enrich_summaries(articles, limit=140):
    import ipaddress, socket
    from html.parser import HTMLParser
    class Metadata(HTMLParser):
        def __init__(self):super().__init__();self.values=[];self.in_p=False;self.paragraphs=[];self.pieces=[];self.in_block=False
        def handle_starttag(self,tag,attrs):
            if tag=='p':self.in_p=True;self.pieces=[]
            if tag in ('script','style','nav','footer'):self.in_block=True
            if tag!='meta':return
            d=dict(attrs);name=(d.get('property') or d.get('name') or '').lower()
            if name in ('og:description','twitter:description','description'):
                value=html.unescape(d.get('content','')).strip()
                if value:self.values.append(value)
        def handle_data(self,data):
            if self.in_p and not self.in_block:self.pieces.append(data)
        def handle_endtag(self,tag):
            if tag=='p':
                para=re.sub(r'\s+',' ',' '.join(self.pieces)).strip()
                if 90<=len(para)<=1300 and not re.search(r'cookie|newsletter|subscribe|advertisement|all rights reserved',para,re.I):self.paragraphs.append(para)
                self.in_p=False;self.pieces=[]
            if tag in ('script','style','nav','footer'):self.in_block=False
    path=BASE/'resumos_fontes.json'
    try:cache=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):cache={}
    def allowed(url):
        parsed=urllib.parse.urlparse(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:return False
        if parsed.hostname.endswith(('.local','.internal')) or parsed.hostname in ('localhost','news.google.com'):return False
        try:
            addresses=socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
            return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
        except (OSError,ValueError):return False
    def fetch_description(url):
        if not allowed(url):return ''
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; JornalDoFabricio/4.7; editorial metadata)','Accept':'text/html'})
            with urllib.request.urlopen(req,timeout=5) as response:
                if response.url!=url and not allowed(response.url):return ''
                if 'html' not in response.headers.get('Content-Type',''):return ''
                payload=response.read(180000).decode('utf-8','replace')
            parser=Metadata();parser.feed(payload)
            for value in parser.values + parser.paragraphs[:2]:
                value=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',value)).strip()
                if len(value)>=45 and not re.search(r'cookie|subscribe|newsletter|cadastre-se|assine agora',value,re.I):
                    # Trecho de metadados limitado; a notícia completa permanece na fonte.
                    return ' '.join(value.split()[:65])
        except Exception:pass
        return ''
    targets=[]
    for a in articles[:limit]:
        if summary_text(a):continue
        url=a.get('url','')
        if url and not cache.get(url):targets.append(url)
    targets=list(dict.fromkeys(targets))[:limit]
    if targets:
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            for url,value in zip(targets,pool.map(fetch_description,targets)):
                cache[url]=value
        path.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding='utf-8')
    for a in articles:
        if not summary_text(a) and cache.get(a.get('url','')):
            a['summary']=cache[a['url']]
    return articles

def illustration_topic(a):
    text=(a.get('title','')+' '+a.get('summary','')).lower()
    if any(x in text for x in ('trump','presidente americano','casa branca')):return 'trump'
    if any(x in text for x in ('drone','ucran','russia','míssil','guerra','bombarde')):return 'guerra'
    if any(x in text for x in ('bitcoin','cripto','mercado','bolsa','dólar','econom')):return 'mercados'
    if any(x in text for x in ('espaço','nasa','foguete','satélite','starlink')):return 'espaco'
    if any(x in text for x in ('futebol','gol','corinthians','jogo','campeonato')):return 'esportes'
    if any(x in text for x in ('china','ásia','índia','asia')):return 'asia'
    return 'mundo'

def create_illustrations():
    folder=BASE/'thumbnails';folder.mkdir(exist_ok=True)
    topics={'trump':('POLÍTICA DOS EUA','★','USA'), 'guerra':('GUERRA E CONFLITOS','✦','CONFLITO'), 'mercados':('ECONOMIA E MERCADOS','↗','MERCADOS'), 'espaco':('ESPAÇO','✧','ESPAÇO'), 'esportes':('ESPORTES','◉','ESPORTE'), 'asia':('ÁSIA','◇','ÁSIA'), 'mundo':('NOTÍCIAS DO MUNDO','◎','MUNDO')}
    for key,(label,symbol,tag) in topics.items():
        svg=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400"><rect width="640" height="400" fill="#0d2236"/><circle cx="515" cy="75" r="160" fill="#183a53"/><path d="M0 335 Q160 230 320 330 T640 300 V400 H0" fill="#1f4960"/><path d="M36 45 H220" stroke="#c9a66a" stroke-width="5"/><text x="42" y="200" fill="#c9a66a" font-family="Georgia,serif" font-size="110">{symbol}</text><text x="42" y="298" fill="white" font-family="Arial,sans-serif" font-size="32" font-weight="bold">{label}</text><text x="42" y="352" fill="#c9a66a" font-family="Arial,sans-serif" font-size="16">ILUSTRAÇÃO TEMÁTICA</text></svg>'''
        (folder/('ilustracao_'+key+'.svg')).write_text(svg,encoding='utf-8')

def balanced(articles, limit=450):
    # Round-robin by section; do not create or relabel stories to fill quotas.
    buckets={}
    for a in articles:
        k=next((v for v in a['sectors'] if v!='geral'),'geral')
        buckets.setdefault(k,[]).append(a)
    for values in buckets.values(): values.sort(key=lambda a:a['published'],reverse=True)
    result=[]
    while len(result)<limit and any(buckets.values()):
        for k in sorted(buckets,key=lambda k:(k=='geral',-len(buckets[k]),k)):
            if buckets[k] and len(result)<limit: result.append(buckets[k].pop(0))
    return result

ENGLISH_WORDS=set("the a an and or for from with after before over amid says said as in on of to by at into about new latest world war protests school behind anger veteran actor dies government budget next test climate crisis refugees peace meeting army chief president says trump china india ukraine russia france pakistan sudan people more than years old how why what where who could would will has have was were are is its their his her this that those these blocked blocking news report".split())

def english_title(title):
    words=re.findall(r"[a-z]+",title.lower())
    hits=sum(w in ENGLISH_WORDS for w in words)
    return hits>=2 and not re.search(r'[ãõáéíóúâêôç]',title.lower())

def translate_titles(articles):
    # Translate foreign titles and meaningful RSS summaries. Untranslated English titles are excluded.
    cache_path=BASE/'traducoes.json'
    try:cache=json.loads(cache_path.read_text(encoding='utf-8'))
    except Exception:cache={}
    candidates=[]
    for a in articles:
        for field in ('title','summary'):
            value=re.sub(r'\s+',' ',a.get(field,'')).strip()
            if value and english_title(value) and value not in cache:
                candidates.append(value[:1000])
    pending=list(dict.fromkeys(candidates))[:800]
    def translate(value):
        try:
            q=urllib.parse.urlencode({'client':'gtx','sl':'auto','tl':'pt','dt':'t','q':value})
            req=urllib.request.Request('https://translate.googleapis.com/translate_a/single?'+q,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=7) as r: result=json.load(r)
            translated=''.join(part[0] for part in result[0] if part and part[0]).strip()
            if translated and translated.casefold()!=value.casefold() and not english_title(translated):return value,translated
        except Exception:pass
        return value,None
    if pending:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for original,translated in pool.map(translate,pending):
                if translated:cache[original]=translated
        cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding='utf-8')
    output=[]
    for a in articles:
        a=dict(a)
        if english_title(a['title']):
            translated=cache.get(a['title'])
            if not translated or english_title(translated):continue
            a['title']=translated
        if english_title(a.get('summary','')):
            a['summary']=cache.get(a['summary'],'')
        if english_title(a.get('summary','')):a['summary']=''
        output.append(a)
    return output

def resolve_publisher_links(articles, limit=110):
    """Best-effort publisher URL extraction; never sends Google News intermediary to translation."""
    from html.parser import HTMLParser
    import ipaddress, socket
    cache_path=BASE/'links_fontes.json'
    try: cache=json.loads(cache_path.read_text(encoding='utf-8'))
    except (OSError, ValueError): cache={}
    class Links(HTMLParser):
        def __init__(self): super().__init__();self.urls=[]
        def handle_starttag(self,tag,attrs):
            d=dict(attrs)
            if tag=='link' and 'canonical' in d.get('rel','').lower():self.urls.append(d.get('href',''))
            if tag=='meta' and d.get('property','').lower()=='og:url':self.urls.append(d.get('content',''))
    def safe(url):
        u=urllib.parse.urlsplit(url)
        if u.scheme!='https' or not u.hostname or u.username or u.password:return False
        if u.hostname in ('news.google.com','www.news.google.com','localhost') or u.hostname.endswith(('.local','.internal','.google.com','.googleusercontent.com')):return False
        try:
            return all(ipaddress.ip_address(i[4][0]).is_global for i in socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM))
        except (OSError,ValueError):return False
    def get(url):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'})
            with urllib.request.urlopen(req,timeout=4) as r:
                target=r.geturl()
                if safe(target):return target
                raw=r.read(90000).decode('utf-8','replace')
            parser=Links();parser.feed(raw)
            return next((u for u in parser.urls if safe(u)), '')
        except Exception:return ''
    pending=[]
    for a in articles[:limit]:
        url=a.get('url','');host=(urllib.parse.urlsplit(url).hostname or '').lower()
        if host in ('news.google.com','www.news.google.com') and url not in cache:pending.append(url)
    pending=list(dict.fromkeys(pending))[:limit]
    if pending:
        with concurrent.futures.ThreadPoolExecutor(max_workers=14) as pool:
            for url,found in zip(pending,pool.map(get,pending)):cache[url]=found
        cache_path.write_text(json.dumps(cache,ensure_ascii=False),encoding='utf-8')
    for a in articles:
        direct=cache.get(a.get('url',''))
        if direct and safe(direct):a['publisher_url']=direct
    return articles

def reading_link(article):
    """Não envia links intermediários do Google News ao tradutor de páginas."""
    url=article.get('publisher_url') or article.get('url','')
    host=(urllib.parse.urlsplit(url).hostname or '').lower()
    if not url.startswith('https://'):
        return url,False
    # O Google News usa links RSS codificados. Traduzir o intermediário produz
    # news-google-com.translate.goog em branco, como no erro reportado.
    if host in ('news.google.com','www.news.google.com'):
        return url,False
    brazilian=host.endswith('.br') or host in {'g1.globo.com','oglobo.globo.com','www.uol.com.br','www.terra.com.br'}
    if brazilian:return url,False
    return 'https://translate.google.com/translate?'+urllib.parse.urlencode({'sl':'auto','tl':'pt-BR','u':url}),True


def main():
    create_illustrations()
    data=engine.report(); arts=translate_titles(enrich_summaries(resolve_publisher_links(source_selector.choose_sources(balanced(data['articles']))))); src=(BASE/'app_original.txt').read_text(encoding='utf-8')
    css=src.split('<style>',1)[1].split('</style>',1)[0].replace('{{','{').replace('}}','}')
    # Keep only original source typography and layout; no backend actions exposed.
    css+='''\n.story{min-height:145px}.story-thumb{display:block}.filters{grid-template-columns:1.4fr 1fr 1fr}.filters button{display:none}.live-note{font-size:11px;color:#65758a;margin-top:9px}.story[hidden]{display:none!important}.pagination button{background:#eef3f8;color:#214767;margin:0 3px}.pagination button:disabled{opacity:.35}.story-foot{clear:none}.story-top{margin-bottom:3px}.abstract{line-height:1.5}.story{padding-top:19px!important;padding-bottom:16px!important}.hero{padding-top:9px!important;padding-bottom:14px!important}.topline{padding-bottom:9px!important}.live-note{display:none}@media(max-width:560px){.filters{grid-template-columns:1fr}.story-thumb{float:none;width:100%;height:175px;margin:0 0 12px}}'''
    css+='\n.translate-action{color:#a8742b!important;font-weight:700;text-decoration:underline;text-underline-offset:3px}.story-foot a{display:inline-block;margin:3px 0}.story h3 a:hover{text-decoration:underline}.translate-action{background:#f5efe3;padding:5px 8px;border-radius:3px;white-space:nowrap}'
    thumbs=BASE/'thumbnails'; count=0
    cards=[]
    for i,a in enumerate(arts,1):
        image=a.get('image_url','') or ''
        if image.startswith('/thumb/'):
            fn=Path(image).name
            if (thumbs/fn).is_file():image='thumbnails/'+fn;count+=1
            else:image=''
        if image and not image.startswith('https://') and not image.startswith('thumbnails/'):image=''
        if not image:
            image='thumbnails/ilustracao_'+illustration_topic(a)+'.svg'
            alt='Ilustração temática, não fotografia do acontecimento'
            cls='story-thumb story-illustration'
        else:
            alt='Imagem da publicação de origem'
            cls='story-thumb'
        img=f'<img class="{cls}" src="{e(image)}" loading="lazy" alt="{alt}" onerror="this.remove()">'
        tags=''.join('<span class="tag">'+e(x.title())+'</span>' for x in a['sectors'])
        summary=e(summary_text(a))
        original_url=a.get('publisher_url') or a['url']
        translated_url,foreign=reading_link(a)
        other_links=[]
        for alt in a.get('other_sources',[]):
            alt_url,alt_translatable=reading_link({'url':alt['url']})
            other_links.append(f'<a href="{e(alt_url)}" target="_blank" rel="noopener noreferrer">{e(alt.get("name") or "Outra fonte")}{" · Português 🇧🇷" if alt_translatable else ""} ↗</a>')
        other_sources_html=(f'<details class="source-options"><summary>Outras coberturas deste acontecimento ({len(other_links)})</summary><div>{"".join(other_links)}</div></details>' if other_links else '')
        source_links=(f'<a class="translate-action" href="{e(translated_url)}" target="_blank" rel="noopener noreferrer"><svg class="br-flag-svg" width="25" height="17" viewBox="0 0 25 17" xmlns="http://www.w3.org/2000/svg" aria-label="Bandeira do Brasil" role="img"><rect width="25" height="17" rx="1" fill="#009739"/><path d="M12.5 1.7 23 8.5 12.5 15.3 2 8.5Z" fill="#FFDF00"/><circle cx="12.5" cy="8.5" r="4.1" fill="#002776"/><path d="M8.7 7.1Q12.5 6.2 16.3 9" fill="none" stroke="white" stroke-width=".85"/></svg> Ler matéria em português ↗</a> · ' if foreign else '')+f'<a href="{e(original_url)}" target="_blank" rel="noopener noreferrer">Fonte original ↗</a>'
        cards.append(f'<article class="story" data-sector="{e("|".join(a["sectors"]))}" data-day="{e(a["published"][:10])}" data-text="{e((a["title"]+" "+a["summary"]+" "+a["source"]).casefold())}">{img}<div class="story-top"><span class="story-index">{i:02d}</span><div class="tags">{tags}</div></div><h3><a href="{e(translated_url)}" target="_blank" rel="noopener noreferrer">{e(a["title"])}</a></h3>{f'<p class="abstract">{summary}</p>' if summary else ''}<div class="story-foot"><span><b>{e(a["source"])}</b> · {e(dt.datetime.fromisoformat(a['published']).astimezone(engine.TZ).strftime('%d/%m/%Y · %H:%M'))} (Brasília)</span>{source_links}</div>{other_sources_html}</article>')
    labels={'internacional':'Internacional','americas':'Américas','europa':'Europa','asia':'Ásia','oriente_medio':'Oriente Médio','oceania':'Oceania','africa':'África','antartida':'Antártida','guerra':'Guerra e conflitos','espaco':'Espaço e exploração espacial','financas':'Finanças','ciencia':'Ciência','agronegocio':'Agronegócio','saude':'Saúde','politica':'Política','logistica':'Logística','tecnologia':'Tecnologia','esportes':'Esportes','economia':'Economia','empresas':'Empresas','sociedade':'Sociedade','energia':'Energia','clima':'Clima','cultura':'Cultura','geopolitica':'Geopolítica'}
    world_sections=['internacional','americas','europa','asia','oriente_medio','oceania','africa','antartida','guerra','espaco']
    option=lambda key:f'<option value="{e(key)}">{e(labels.get(key,key.title()))}</option>'
    sectors='<optgroup label="Mundo e regiões">'+''.join(option(k) for k in world_sections if k in engine.SECTORS)+'</optgroup><optgroup label="Outras editorias">'+''.join(option(k) for k in sorted(engine.SECTORS) if k not in world_sections)+'</optgroup>'
    today=data['date']; yesterday=(dt.date.fromisoformat(today)-dt.timedelta(days=1)).isoformat()
    last=data['last_run']; status=f'{last["success"]} canais responderam · {last["fail"]} falharam' if last else 'Ainda não houve coleta bem-sucedida.'
    market_labels=[('USD/BRL','Dólar comercial'),('EUR/BRL','Euro comercial'),('IBOV','Ibovespa · B3'),('BRENT','Petróleo Brent'),('S&P 500','S&P 500'),('NASDAQ','Nasdaq'),('BTC/USD','Bitcoin')]
    try: market_snapshot=json.loads((BASE/'mercados.json').read_text(encoding='utf-8'))
    except (OSError,ValueError,TypeError): market_snapshot={}
    snapshots={i.get('symbol'):i for i in market_snapshot.get('items',[]) if isinstance(i,dict)}
    def market_row(symbol,label):
        item=snapshots.get(symbol,{})
        value=e(item.get('value') or '—')
        change=item.get('change')
        valid=isinstance(change,(float,int)) and not isinstance(change,bool)
        kind=('up' if change>0 else 'down' if change<0 else 'neutral') if valid else 'neutral'
        direction=('▲ +' if change>0 else '▼ ' if change<0 else '● ') if valid else ''
        change_label=(direction+f'{change:.2f}%'.replace('.',',')+(' / 24h' if item.get('change_period')=='24h' else '')) if valid else 'Variação n/d'
        info=(' · '.join(str(x) for x in (item.get('status'),item.get('asof'),item.get('source')) if x) if item.get('value') else 'Sem cotação')
        return (f'<div class="market-row" data-symbol="{e(symbol)}"><div class="market-detail"><strong>{e(label)}</strong><small>{e(symbol)}</small></div>'
                f'<div class="market-right"><b class="market-value">{value}</b><small class="market-change {kind}">{e(change_label)}</small>'
                f'<small class="market-meta">{e(info)}</small></div></div>')
    market_rows=''.join(market_row(symbol,label) for symbol,label in market_labels)
    css+='''
.hero{padding:0 0 2px!important;min-height:0!important}.hero .gold{margin:0!important}.topline{margin-bottom:4px!important}.shell{max-width:1380px!important;padding-top:24px!important}.workspace{max-width:1320px!important;display:grid!important;grid-template-columns:minmax(0,1fr) 292px;gap:24px;align-items:start}.feed-column{min-width:0}.market-panel{position:sticky;top:16px;background:#0d2135;color:#e9eef3;padding:20px 17px;border:1px solid #c2a47755;box-shadow:0 10px 35px #081b2a20}.market-head{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #ffffff25;padding-bottom:12px;margin-bottom:8px}.market-head h2{font:700 13px Georgia,serif;letter-spacing:.12em;margin:0;color:#c9a66a}.market-live{font:10px Arial,sans-serif;color:#b6c6d4;letter-spacing:.06em}.market-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:13px 0;border-bottom:1px solid #ffffff18}.market-row strong{display:block;font:600 12px Arial,sans-serif}.market-row small{display:block;color:#9fb2c2;font-size:10px;margin-top:5px}.market-right{text-align:right}.market-value{font:700 15px Arial,sans-serif;white-space:nowrap;font-variant-numeric:tabular-nums}.market-change.up{color:#85d2ac}.market-change.down{color:#f3a3a3}.market-disclaimer{font:11px/1.5 Arial,sans-serif;color:#b5c5d0;margin-top:14px}.world-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:2px solid #c5a26a;margin:20px 0 13px;padding-bottom:10px;font:700 18px Georgia,serif;color:#0b1c2d}.news-heading{margin-top:22px!important}.world-heading small{font:11px Arial,sans-serif;color:#68798a}.world-strip{display:flex;gap:10px;overflow:auto;margin-bottom:14px}.world-item{min-width:205px;flex:1;background:#fff;border:1px solid #e6e3df;padding:13px;text-decoration:none;color:#172c3a;font:14px/1.35 Georgia,serif}.world-item small{display:block;color:#977e57;font:10px Arial,sans-serif;margin-bottom:7px}.story{padding:14px 19px!important}.story h3{font-size:24px!important}.story-thumb{width:190px;height:125px}.hero{padding-top:2px!important;padding-bottom:9px!important}.topline{padding-bottom:6px!important}.shell .panel{padding:18px!important}@media(max-width:980px){.workspace{grid-template-columns:1fr!important}.market-panel{position:static;grid-row:1}.market-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:18px}}@media(max-width:520px){.market-grid{grid-template-columns:1fr}.world-item{min-width:180px}}@media print{.market-panel,.world-strip,.world-heading{display:none!important}.workspace{display:block!important}}
'''
    world=[a for a in arts if any(x in a['sectors'] for x in ('internacional','guerra','americas','europa','asia','oriente_medio','oceania','africa','antartida','espaco'))][:32]
    def panorama_image(a):
        image=a.get('image_url','') or ''
        if image.startswith('/thumb/'):
            filename=Path(image).name
            image='thumbnails/'+filename if (thumbs/filename).is_file() else ''
        if not image.startswith(('https://','thumbnails/')):image='thumbnails/ilustracao_'+illustration_topic(a)+'.svg'
        return f'<img src="{e(image)}" alt="Imagem ilustrativa ou da fonte original" loading="lazy" onerror="this.onerror=null;this.src=\'thumbnails/ilustracao_mundo.svg\'">'
    world_strip='<div class="world-heading">PANORAMA GLOBAL <span class="world-controls"><button type="button" id="world-prev" aria-label="Notícias anteriores">← Anterior</button><button type="button" id="world-next" aria-label="Próximas notícias">Próximas →</button></span></div><div class="world-strip" id="world-strip">'+''.join(f'<a class="world-item" href="{e(reading_link(a)[0])}" target="_blank" rel="noopener noreferrer">{panorama_image(a)}<small>{e(a["source"])}</small>{e(a["title"])}</a>' for a in world)+'</div><div class="world-dots" id="world-dots" aria-label="Páginas do panorama"></div>' if world else '' 
    css+='''
.world-controls{display:flex;gap:7px}.world-controls button{border:1px solid #c9a66a;background:#0d2135;color:#d8b36d;font:12px Arial,sans-serif;padding:7px 10px;cursor:pointer}.world-controls button:hover{background:#193b57}.world-strip{scroll-snap-type:x mandatory;scroll-behavior:smooth;scrollbar-width:none;overscroll-behavior-inline:contain}.world-item{flex:0 0 calc((100% - 30px)/4);box-sizing:border-box;scroll-snap-align:start;min-width:0}.story-thumb{object-fit:cover}.story-illustration{border:1px solid #d9d2c8}.world-item img{width:100%;height:78px;object-fit:cover;margin-bottom:8px}@media(max-width:750px){.world-item{flex-basis:calc((100% - 10px)/2)}.world-heading{flex-wrap:wrap}}@media(max-width:450px){.world-item{flex-basis:85%}.world-controls button{font-size:11px}}
'''
    css+='''
.world-strip::-webkit-scrollbar{display:none}.world-dots{display:flex;justify-content:center;align-items:center;gap:8px;margin:0 0 18px}.world-dot{width:9px;height:9px;border-radius:50%;border:0;background:#c9c9c9;cursor:pointer;padding:0}.world-dot.active{background:#c9a66a;transform:scale(1.2)}.market-change.up{color:#66d69a!important}.market-change.down{color:#ff8888!important}.market-head h2{color:#c9a66a!important}.market-value{font-family:Arial,sans-serif!important;font-variant-numeric:tabular-nums!important;letter-spacing:0!important}.market-right{min-width:110px}.world-controls button{background:#0d2135!important;color:#d8b36d!important;border-color:#c9a66a!important}.abstract{max-width:80ch;line-height:1.65!important}.story-foot a{white-space:nowrap;margin-left:8px}.story:has(.abstract){min-height:185px}'''
    css+"""
@media(max-width:980px){
 .workspace{display:flex!important;flex-direction:column!important;gap:22px!important}
 .feed-column{order:1;width:100%!important;min-width:0}
 .market-panel{order:2!important;grid-row:auto!important;position:static!important;width:100%!important;box-sizing:border-box}
 .shell{padding-left:16px!important;padding-right:16px!important}
}
@media(max-width:600px){
 .topline{display:flex!important;flex-wrap:wrap!important;gap:12px!important}
 .brand{font-size:24px!important;letter-spacing:.09em!important}
 .micro{font-size:10px!important}
 .shell{padding-left:12px!important;padding-right:12px!important;padding-top:16px!important}
 .shell .panel{padding:14px!important}
 .filters{grid-template-columns:1fr!important;gap:10px!important}
 .world-heading{font-size:19px!important;align-items:center!important;flex-wrap:wrap!important}
 .world-controls{margin-left:auto!important}
 .world-controls button{padding:7px 8px!important;font-size:11px!important}
 .world-strip{gap:10px!important;overflow-x:auto!important;scroll-snap-type:x mandatory!important}
 .world-item{flex:0 0 100%!important;min-width:100%!important;max-width:100%!important;min-height:0!important;padding:12px!important}
 .world-item img{height:170px!important;object-fit:cover!important;border-radius:2px!important}
 .story{padding:14px!important;min-height:0!important}
 .story h3{font-size:clamp(21px,5.6vw,26px)!important;line-height:1.2!important;overflow-wrap:anywhere!important}
 .story-thumb{width:100%!important;height:190px!important;float:none!important;display:block!important;margin:0 0 13px!important;object-fit:cover!important}
 .story-foot{display:flex!important;flex-wrap:wrap!important;gap:10px!important}
 .market-grid{grid-template-columns:1fr!important}
 .market-panel{padding:18px 16px!important}
}
"""
    css += '''
.source-options{margin-top:9px;font:12px Arial,sans-serif;color:#62768c}.source-options summary{cursor:pointer;width:max-content;max-width:100%}.source-options div{display:flex;flex-wrap:wrap;gap:6px 14px;padding-top:8px}.source-options a{color:#1b4a67;text-decoration:underline;text-underline-offset:2px}.source-options a:hover{color:#9b753f}
'''
    # Paginação editorial: alinhamento central, azul-marinho e dourado.
    css += '''
.pagination{display:flex!important;align-items:center!important;justify-content:center!important;gap:16px!important;flex-wrap:wrap!important;margin:26px auto 32px!important;width:100%!important;text-align:center!important}
.pagination>div{display:flex!important;justify-content:center!important;align-items:center!important;gap:12px!important;flex-wrap:wrap!important;width:100%!important}
.pagination button,.pagination button#prev,.pagination button#next{background:#0b2032!important;color:#d7aa60!important;border:1px solid #b98a42!important;border-radius:5px!important;font-family:Arial,Helvetica,sans-serif!important;font-weight:700!important;font-size:14px!important;padding:12px 22px!important;min-height:44px!important;min-width:135px!important;cursor:pointer!important;box-shadow:none!important;opacity:1!important}
.pagination button:hover:not(:disabled){background:#16374f!important;color:#f0c57e!important}
.pagination button:disabled{opacity:.42!important;cursor:not-allowed!important}
.pagination #counter{display:block!important;width:100%!important;text-align:center!important;font-family:Arial,Helvetica,sans-serif!important;font-size:12px!important;color:#64748b!important}
@media(max-width:560px){.pagination{gap:12px!important}.pagination>div{gap:8px!important}.pagination button,.pagination button#prev,.pagination button#next{min-width:125px!important;padding:12px 14px!important}}
'''
    css += """
.br-flag{display:inline-block;width:22px;height:15px;vertical-align:-3px;margin-right:5px;background:#009739;position:relative;border-radius:1px;overflow:hidden}
.br-flag:before{content:'';position:absolute;left:4px;top:2px;width:14px;height:11px;background:#ffdf00;clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%)}
.br-flag:after{content:'';position:absolute;left:9px;top:5px;width:5px;height:5px;background:#002776;border-radius:50%}
.br-flag-svg{display:inline-block!important;flex:0 0 25px!important;width:25px!important;height:17px!important;vertical-align:middle!important;margin-right:5px!important}.translate-action{display:inline-flex!important;align-items:center;gap:3px;background:#f5efe3!important;color:#916321!important;font:700 13px Arial,sans-serif!important;padding:7px 10px!important}
.pagination button:disabled{opacity:1!important;color:#d7aa60!important;filter:brightness(.8);cursor:not-allowed!important}
"""
    # Cotações compactas, com números tabulares e variação cromática explícita.
    css+='''
.market-head h2{color:#d4ae73!important;letter-spacing:.12em}
.market-row{align-items:flex-start!important;gap:7px!important;padding:15px 0!important}
.market-detail{min-width:0;flex:1}
.market-right{min-width:124px!important;max-width:160px;display:flex;flex-direction:column;align-items:flex-end;gap:5px;font-family:Arial,Helvetica,sans-serif!important}
.market-value{font-family:Arial,Helvetica,sans-serif!important;font-variant-numeric:tabular-nums!important;font-feature-settings:'tnum'!important;font-weight:700!important;font-size:16px!important;color:#f9fbff!important}
.market-change{box-sizing:border-box;display:inline-flex!important;justify-content:center;align-items:center;border-radius:4px;padding:5px 7px!important;width:max-content;max-width:100%;font:700 12px Arial,Helvetica,sans-serif!important;font-variant-numeric:tabular-nums!important;letter-spacing:0!important}
.market-change.up{background:#0d6946!important;color:white!important}
.market-change.down{background:#a72e3c!important;color:white!important}
.market-change.neutral{background:#26394d!important;color:#c7d2df!important}
.market-meta{font:10px/1.45 Arial,Helvetica,sans-serif!important;color:#9fb5c5!important;text-align:right;overflow-wrap:anywhere;max-width:155px}
@media(max-width:980px){.market-right{max-width:175px}}
'''
    page=f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Jornal do Fabricio — cobertura global e brasileira"><title>Jornal do Fabricio | Edição Exclusiva</title><style>{css}</style></head><body><header class="top"><div class="topline"><div class="brand">JORNAL DO FABRICIO</div><div class="micro">Edição Exclusiva · {dt.date.fromisoformat(today):%d/%m/%Y}</div></div><div class="hero"><div class="gold"></div></div></header><main class="shell"><div class="workspace"><div class="feed-column"><section class="panel"><div class="filters"><input id="search" placeholder="Pesquisar manchetes ou fontes" aria-label="Pesquisar"><select id="sector" aria-label="Editoria"><option value="">Todas as editorias</option>{sectors}</select><select id="day" aria-label="Período"><option value="">Hoje e ontem</option><option value="{today}">Hoje</option><option value="{yesterday}">Ontem</option></select></div></section>{world_strip}<div class="world-heading news-heading">NOTÍCIAS</div><div id="stories">{''.join(cards) or '<div class="empty">Nenhuma notícia coletada ainda. Aguarde a primeira atualização automática.</div>'}</div><div class="pagination" style="display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%;margin:30px auto;gap:14px"><span id="counter" style="text-align:center;width:100%"></span><div style="display:flex;justify-content:center;gap:14px;flex-wrap:wrap;width:100%"><button id="prev" type="button" style="background:#0b2032!important;color:#d7aa60!important;border:1px solid #b98a42!important;font:700 15px Arial,sans-serif!important;padding:13px 24px!important;min-width:145px!important;opacity:1!important">← Anterior</button><button id="next" type="button" style="background:#0b2032!important;color:#d7aa60!important;border:1px solid #b98a42!important;font:700 15px Arial,sans-serif!important;padding:13px 24px!important;min-width:145px!important;opacity:1!important">Próxima →</button></div></div></div><aside class="market-panel" aria-label="Painel de mercados"><div class="market-head"><h2>MERCADOS EM FOCO</h2></div><div class="market-grid">{market_rows}</div><p class="market-disclaimer" id="market-status">Carregando cotações disponíveis…</p><p class="market-disclaimer">Dados indicativos, sujeitos a atraso. Índices sem fonte validada ficam indisponíveis; nenhuma cotação é simulada.</p></aside></div><footer class="technical-footer"><div class="footer-inner"><div class="footer-brand"><span>JORNAL DO FABRICIO</span><small>EDIÇÃO EXCLUSIVA · {dt.date.fromisoformat(today):%d/%m/%Y}</small></div><div class="footer-links"><details><summary>Exportação e impressão</summary><p><a class="footer-tool" href="noticias.csv">Exportar CSV ↗</a> &nbsp; <button class="footer-print" onclick="window.print()">Imprimir / Salvar PDF</button></p></details><details><summary>Estado da atualização e avisos técnicos</summary><p>{e(status)} · Rascunho automatizado não certificado</p><p>Última geração: {e(dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes'))} UTC</p></details><details><summary>Critérios e limitações</summary><p>Atualização conforme a agenda configurada no GitHub Actions; o navegador consulta novas versões a cada minuto. Feeds RSS e agregadores; títulos e datas dependem das fontes. Seleção exploratória, sem certificação editorial. Fotografias apenas quando fornecidas ou acessíveis legitimamente nas fontes; nenhuma imagem é inventada. A execução agendada pode atrasar ou falhar. Links levam à publicação original.</p></details></div><div class="footer-bottom">© Jornal do Fabricio · Publicação pública · Informações sujeitas à verificação nas fontes originais.</div></div></footer></main><script>
const strip=document.querySelector('#world-strip');if(strip){{const jump=()=>Math.max(210,(strip.querySelector('.world-item')?.getBoundingClientRect().width||210)+10);document.querySelector('#world-prev').onclick=()=>strip.scrollBy({{left:-jump(),behavior:'smooth'}});document.querySelector('#world-next').onclick=()=>strip.scrollBy({{left:jump(),behavior:'smooth'}});let sx=0,sl=0;strip.addEventListener('pointerdown',ev=>{{if(ev.pointerType==='mouse'){{sx=ev.clientX;sl=strip.scrollLeft;}}}});strip.addEventListener('pointerup',ev=>{{if(ev.pointerType==='mouse'&&Math.abs(ev.clientX-sx)>35){{strip.scrollLeft=sl+sx-ev.clientX;}}}});}}
const dots=document.querySelector('#world-dots');if(strip&&dots){{const items=[...strip.querySelectorAll('.world-item')];const visible=()=>window.matchMedia('(max-width:600px)').matches?1:window.matchMedia('(max-width:750px)').matches?2:4;const updateDots=()=>{{const n=Math.ceil(items.length/visible());dots.innerHTML='';for(let i=0;i<n;i++){{let b=document.createElement('button');b.type='button';b.className='world-dot'+(i===Math.min(n-1,Math.round(strip.scrollLeft/Math.max(1,strip.clientWidth)))?' active':'');b.setAttribute('aria-label','Ir ao grupo '+(i+1));b.onclick=()=>items[i*visible()]?.scrollIntoView({{behavior:'smooth',block:'nearest',inline:'start'}});dots.appendChild(b);}}}};strip.addEventListener('scroll',()=>requestAnimationFrame(updateDots));window.addEventListener('resize',updateDots);updateDots();}}
const cards=[...document.querySelectorAll('.story')],search=document.querySelector('#search'),sector=document.querySelector('#sector'),day=document.querySelector('#day');let page=0,matching=[];
function render(reset=true){{if(reset)page=0;let term=search.value.trim().toLocaleLowerCase('pt-BR');matching=cards.filter(x=>(!term||x.dataset.text.includes(term))&&(!sector.value||x.dataset.sector.split('|').includes(sector.value))&&(!day.value||x.dataset.day===day.value));let total=Math.max(1,Math.ceil(matching.length/30));page=Math.max(0,Math.min(page,total-1));cards.forEach(x=>x.hidden=true);matching.slice(page*30,(page+1)*30).forEach(x=>x.hidden=false);document.querySelector('#counter').textContent=`Página ${{page+1}} de ${{total}} · ${{matching.length}} notícias`;document.querySelector('#prev').disabled=page===0;document.querySelector('#next').disabled=page>=total-1;}}
[search,sector,day].forEach(x=>x.addEventListener(x===search?'input':'change',()=>render()));document.querySelector('#prev').onclick=()=>{{page--;render(false);window.scrollTo(0,180)}};document.querySelector('#next').onclick=()=>{{page++;render(false);window.scrollTo(0,180)}};render();
function showMarket(item){{
const row=[...document.querySelectorAll('.market-row')].find(x=>x.dataset.symbol===item.symbol);
if(!row)return;
row.querySelector('.market-value').textContent=item.value||'—';
const change=row.querySelector('.market-change');
const valid=typeof item.change==='number'&&Number.isFinite(item.change);
const value=valid?item.change:0;
change.className='market-change '+(valid?(value>0?'up':value<0?'down':'neutral'):'neutral');
const period=item.change_period==='24h'?' / 24h':'';
change.textContent=valid?(value>0?'▲ +':value<0?'▼ ':'● ')+value.toFixed(2).replace('.',',')+'%'+period:'Variação n/d';
row.querySelector('.market-meta').textContent=item.value?[item.status,item.asof,item.source].filter(Boolean).join(' · '):'Sem cotação';
}}
let lastBtcBrowser=0;
async function refreshMarkets(){{try{{
const r=await fetch('mercados.json?t='+Date.now(),{{cache:'no-store'}});
if(!r.ok)throw Error('mercados indisponíveis');
const data=await r.json();
for(const item of data.items||[]){{if(item.symbol!=='BTC/USD'||Date.now()-lastBtcBrowser>120000)showMarket(item);}}
const time=new Date(data.checked_at);
document.querySelector('#market-status').textContent='Última consulta: '+(isNaN(time)?'indisponível':time.toLocaleString('pt-BR',{{timeZone:'America/Sao_Paulo'}}))+' (Brasília). A tela consulta novos dados a cada 30 segundos; não implica negociação em tempo real.';
}}catch(err){{document.querySelector('#market-status').textContent='Não foi possível atualizar o painel; valores anteriores podem estar desatualizados.';}}
}}
refreshMarkets();setInterval(refreshMarkets,30000);
// Cotação BTC e variação de 24 horas da MESMA bolsa. Quando o navegador
// bloqueia acesso direto à API, permanece o snapshot do GitHub.
async function refreshBitcoinBrowser(){{try{{
const reply=await fetch('https://api.exchange.coinbase.com/products/BTC-USD/stats',{{cache:'no-store',mode:'cors'}});
if(!reply.ok)throw Error('cotação indisponível');
const stats=await reply.json();
const price=Number(stats.last),opening=Number(stats.open);
if(!(Number.isFinite(price)&&Number.isFinite(opening)&&price>0&&opening>0))return;
const change=(price/opening-1)*100;
const formatted=price.toLocaleString('pt-BR',{{minimumFractionDigits:2,maximumFractionDigits:2}});
lastBtcBrowser=Date.now();
showMarket({{symbol:'BTC/USD',value:'US$ '+formatted,change:change,change_period:'24h',source:'Coinbase Exchange',status:'cotação no navegador (sujeita a atraso)',asof:new Date().toLocaleString('pt-BR',{{timeZone:'America/Sao_Paulo'}})+' (Brasília)'}});
}}catch(_err){{/* O snapshot guardado continua visível. */}}
}}
refreshBitcoinBrowser();setInterval(refreshBitcoinBrowser,60000);
let version='';async function check(){{try{{let r=await fetch('version.json?ts='+Date.now(),{{cache:'no-store'}});if(!r.ok)return;let v=(await r.json()).version;if(version&&v!==version)location.reload();version=v;}}catch(e){{}}}}check();setInterval(check,60000);
</script></body></html>'''
    (BASE/'index.html').write_text(page,encoding='utf-8')
    (BASE/'version.json').write_text(json.dumps({'version':dt.datetime.now(dt.timezone.utc).isoformat()}))
    with (BASE/'noticias.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['Título','Fonte','Data UTC','Editorias','Link']);w.writerows([a['title'],a['source'],a['published'],', '.join(a['sectors']),a['url']] for a in arts)
    print('Site gerado:',len(arts),'notícias,',count,'imagens locais,',len(page),'caracteres')
if __name__=='__main__':main()
