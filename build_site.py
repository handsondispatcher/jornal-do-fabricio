import csv, datetime as dt, html, io, json, re, shutil, urllib.parse, urllib.request, concurrent.futures, sqlite3, time
from pathlib import Path
import engine
BASE=Path(__file__).parent

def e(s): return html.escape(str(s or ''),quote=True)

def summary_text(article):
    title=re.sub(r'\s+', ' ', article['title']).strip()
    raw=re.sub(r'\s+', ' ', article.get('summary','')).strip()
    source=article.get('source','')
    if raw.casefold().startswith(title.casefold()):
        raw=raw[len(title):].lstrip(' -–—:|')
    if source and raw.casefold() in (source.casefold(), ''): raw=''
    if len(raw)<65 or raw.casefold() in title.casefold():
        return 'Leia a reportagem completa na publicação de origem.'
    return raw[:360].rstrip(' ,;')

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

def english_title(title):
    words=re.findall(r"[a-z]+",title.lower())
    markers={'deepens','refugees','blocking','crisis','aid','strikes','attack','breaking','the','with','after','over','amid','says','against','hits','out','for','from','war','as','and','on','its','new','china','trump','russia','ukraine','world','could','would','will','has','have','are','was','were','into','at','in','to','of','by'}
    return sum(w in markers for w in words)>=2 and not re.search(r'[ãõáéíóúâêôç]',title.lower())

def translate_titles(articles):
    # Translation is best effort. Do not publish untranslated English headlines.
    cache_path=BASE/'traducoes.json'
    try:cache=json.loads(cache_path.read_text(encoding='utf-8'))
    except Exception:cache={}
    pending=list(dict.fromkeys(a['title'] for a in articles if english_title(a['title']) and a['title'] not in cache))[:450]
    def translate(title):
        try:
            q=urllib.parse.urlencode({'client':'gtx','sl':'en','tl':'pt','dt':'t','q':title})
            req=urllib.request.Request('https://translate.googleapis.com/translate_a/single?'+q,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=5) as r: result=json.load(r)
            translated=''.join(part[0] for part in result[0] if part and part[0]).strip()
            if translated and translated.casefold()!=title.casefold() and not english_title(translated):return title,translated
        except Exception:pass
        return title,None
    if pending:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for title,value in pool.map(translate,pending):
                if value:cache[title]=value
        cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding='utf-8')
    output=[]
    for a in articles:
        if english_title(a['title']):
            translated=cache.get(a['title'])
            if not translated:continue
            a=dict(a,title=translated)
        output.append(a)
    return output

def main():
    create_illustrations()
    data=engine.report(); arts=translate_titles(balanced(data['articles'])); src=(BASE/'app_original.txt').read_text(encoding='utf-8')
    css=src.split('<style>',1)[1].split('</style>',1)[0].replace('{{','{').replace('}}','}')
    # Keep only original source typography and layout; no backend actions exposed.
    css+='''\n.story{min-height:145px}.story-thumb{display:block}.filters{grid-template-columns:1.4fr 1fr 1fr}.filters button{display:none}.live-note{font-size:11px;color:#65758a;margin-top:9px}.story[hidden]{display:none!important}.pagination button{background:#eef3f8;color:#214767;margin:0 3px}.pagination button:disabled{opacity:.35}.story-foot{clear:none}.story-top{margin-bottom:3px}.abstract{line-height:1.5}.story{padding-top:19px!important;padding-bottom:16px!important}.hero{padding-top:9px!important;padding-bottom:14px!important}.topline{padding-bottom:9px!important}.live-note{display:none}@media(max-width:560px){.filters{grid-template-columns:1fr}.story-thumb{float:none;width:100%;height:175px;margin:0 0 12px}}'''
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
        cards.append(f'<article class="story" data-sector="{e("|".join(a["sectors"]))}" data-day="{e(a["published"][:10])}" data-text="{e((a["title"]+" "+a["summary"]+" "+a["source"]).casefold())}">{img}<div class="story-top"><span class="story-index">{i:02d}</span><div class="tags">{tags}</div></div><h3><a href="{e(a["url"])}" target="_blank" rel="noopener noreferrer">{e(a["title"])}</a></h3><p class="abstract">{summary}</p><div class="story-foot"><span><b>{e(a["source"])}</b> · {e(dt.datetime.fromisoformat(a['published']).astimezone(engine.TZ).strftime('%d/%m/%Y · %H:%M'))} (Brasília)</span><a href="{e(a["url"])}" target="_blank" rel="noopener noreferrer">Abrir fonte ↗</a></div></article>')
    labels={'internacional':'Internacional','americas':'Américas','europa':'Europa','asia':'Ásia','oriente_medio':'Oriente Médio','oceania':'Oceania','africa':'África','antartida':'Antártida','guerra':'Guerra e conflitos','espaco':'Espaço e exploração espacial','financas':'Finanças','ciencia':'Ciência','agronegocio':'Agronegócio','saude':'Saúde','politica':'Política','logistica':'Logística','tecnologia':'Tecnologia','esportes':'Esportes','economia':'Economia','empresas':'Empresas','sociedade':'Sociedade','energia':'Energia','clima':'Clima','cultura':'Cultura','geopolitica':'Geopolítica'}
    world_sections=['internacional','americas','europa','asia','oriente_medio','oceania','africa','antartida','guerra','espaco']
    option=lambda key:f'<option value="{e(key)}">{e(labels.get(key,key.title()))}</option>'
    sectors='<optgroup label="Mundo e regiões">'+''.join(option(k) for k in world_sections if k in engine.SECTORS)+'</optgroup><optgroup label="Outras editorias">'+''.join(option(k) for k in sorted(engine.SECTORS) if k not in world_sections)+'</optgroup>'
    today=data['date']; yesterday=(dt.date.fromisoformat(today)-dt.timedelta(days=1)).isoformat()
    last=data['last_run']; status=f'{last["success"]} canais responderam · {last["fail"]} falharam' if last else 'Ainda não houve coleta bem-sucedida.'
    market_labels=[('USD/BRL','Dólar comercial'),('EUR/BRL','Euro comercial'),('IBOV','Ibovespa · B3'),('IFIX','Fundos imobiliários'),('S&P 500','S&P 500'),('NASDAQ','Nasdaq'),('BTC/USD','Bitcoin')]
    market_rows=''.join(f'<div class="market-row" data-symbol="{e(symbol)}"><div><strong>{e(label)}</strong><small>{e(symbol)}</small></div><div class="market-right"><b class="market-value">—</b><small class="market-change">Sem cotação</small></div></div>' for symbol,label in market_labels)
    try:
        snapshot=json.loads((BASE/'mercados.json').read_text(encoding='utf-8'))
        for item in snapshot.get('items',[]):
            if item.get('value'):
                symbol=e(item.get('symbol',''))
                marker=f'data-symbol="{symbol}"'
                start=market_rows.find(marker)
                if start>=0:
                    stop=market_rows.find('</div></div>',start)
                    if stop>=0:
                        part=market_rows[start:stop]
                        part=part.replace('<b class="market-value">—</b>',f'<b class="market-value">{e(item["value"])}</b>')
                        part=part.replace('Sem cotação',e('Último fechamento: '+str(item.get('asof') or '')+' · '+str(item.get('source') or '')))
                        market_rows=market_rows[:start]+part+market_rows[stop:]
    except (OSError,ValueError,TypeError):pass
    css+='''
.hero{padding:0 0 2px!important;min-height:0!important}.hero .gold{margin:0!important}.topline{margin-bottom:4px!important}.shell{max-width:1380px!important;padding-top:24px!important}.workspace{max-width:1320px!important;display:grid!important;grid-template-columns:minmax(0,1fr) 292px;gap:24px;align-items:start}.feed-column{min-width:0}.market-panel{position:sticky;top:16px;background:#0d2135;color:#e9eef3;padding:20px 17px;border:1px solid #c2a47755;box-shadow:0 10px 35px #081b2a20}.market-head{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #ffffff25;padding-bottom:12px;margin-bottom:8px}.market-head h2{font:700 13px Georgia,serif;letter-spacing:.12em;margin:0;color:#e9d4a8}.market-live{font:10px Arial,sans-serif;color:#b6c6d4;letter-spacing:.06em}.market-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:13px 0;border-bottom:1px solid #ffffff18}.market-row strong{display:block;font:600 12px Arial,sans-serif}.market-row small{display:block;color:#9fb2c2;font-size:10px;margin-top:5px}.market-right{text-align:right}.market-value{font:600 16px Georgia,serif;white-space:nowrap}.market-change.up{color:#85d2ac}.market-change.down{color:#f3a3a3}.market-disclaimer{font:11px/1.5 Arial,sans-serif;color:#b5c5d0;margin-top:14px}.world-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:2px solid #c5a26a;margin:20px 0 13px;padding-bottom:10px;font:700 18px Georgia,serif;color:#0b1c2d}.news-heading{margin-top:22px!important}.world-heading small{font:11px Arial,sans-serif;color:#68798a}.world-strip{display:flex;gap:10px;overflow:auto;margin-bottom:14px}.world-item{min-width:205px;flex:1;background:#fff;border:1px solid #e6e3df;padding:13px;text-decoration:none;color:#172c3a;font:14px/1.35 Georgia,serif}.world-item small{display:block;color:#977e57;font:10px Arial,sans-serif;margin-bottom:7px}.story{padding:14px 19px!important}.story h3{font-size:24px!important}.story-thumb{width:190px;height:125px}.hero{padding-top:2px!important;padding-bottom:9px!important}.topline{padding-bottom:6px!important}.shell .panel{padding:18px!important}@media(max-width:980px){.workspace{grid-template-columns:1fr!important}.market-panel{position:static;grid-row:1}.market-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:18px}}@media(max-width:520px){.market-grid{grid-template-columns:1fr}.world-item{min-width:180px}}@media print{.market-panel,.world-strip,.world-heading{display:none!important}.workspace{display:block!important}}
'''
    world=[a for a in arts if any(x in a['sectors'] for x in ('internacional','guerra','americas','europa','asia','oriente_medio','oceania','africa','antartida','espaco'))][:32]
    def panorama_image(a):
        image=a.get('image_url','') or ''
        if image.startswith('/thumb/'):
            filename=Path(image).name
            image='thumbnails/'+filename if (thumbs/filename).is_file() else ''
        if not image.startswith(('https://','thumbnails/')):image='thumbnails/ilustracao_'+illustration_topic(a)+'.svg'
        return f'<img src="{e(image)}" alt="Imagem ilustrativa ou da fonte original" loading="lazy" onerror="this.onerror=null;this.src=\'thumbnails/ilustracao_mundo.svg\'">'
    world_strip='<div class="world-heading">PANORAMA GLOBAL <span class="world-controls"><button type="button" id="world-prev" aria-label="Notícias anteriores">← Anterior</button><button type="button" id="world-next" aria-label="Próximas notícias">Próximas →</button></span></div><div class="world-strip" id="world-strip">'+''.join(f'<a class="world-item" href="{e(a["url"])}" target="_blank" rel="noopener noreferrer">{panorama_image(a)}<small>{e(a["source"])}</small>{e(a["title"])}</a>' for a in world)+'</div>' if world else '' 
    css+='''
.world-controls{display:flex;gap:7px}.world-controls button{border:1px solid #d7c19a;background:#fff;color:#16324a;font:12px Arial,sans-serif;padding:7px 10px;cursor:pointer}.world-controls button:hover{background:#f7eddd}.world-strip{scroll-snap-type:x mandatory;scroll-behavior:smooth;scrollbar-width:thin;overscroll-behavior-inline:contain}.world-item{flex:0 0 calc((100% - 30px)/4);box-sizing:border-box;scroll-snap-align:start;min-width:0}.story-thumb{object-fit:cover}.story-illustration{border:1px solid #d9d2c8}.world-item img{width:100%;height:78px;object-fit:cover;margin-bottom:8px}@media(max-width:750px){.world-item{flex-basis:calc((100% - 10px)/2)}.world-heading{flex-wrap:wrap}}@media(max-width:450px){.world-item{flex-basis:85%}.world-controls button{font-size:11px}}
'''
    css+="""
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
    page=f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Jornal do Fabricio — cobertura global e brasileira"><title>Jornal do Fabricio | Edição Exclusiva</title><style>{css}</style></head><body><header class="top"><div class="topline"><div class="brand">JORNAL DO FABRICIO</div><div class="micro">Edição Exclusiva · {dt.date.fromisoformat(today):%d/%m/%Y}</div></div><div class="hero"><div class="gold"></div></div></header><main class="shell"><div class="workspace"><div class="feed-column"><section class="panel"><div class="filters"><input id="search" placeholder="Pesquisar manchetes ou fontes" aria-label="Pesquisar"><select id="sector" aria-label="Editoria"><option value="">Todas as editorias</option>{sectors}</select><select id="day" aria-label="Período"><option value="">Hoje e ontem</option><option value="{today}">Hoje</option><option value="{yesterday}">Ontem</option></select></div></section>{world_strip}<div class="world-heading news-heading">NOTÍCIAS</div><div id="stories">{''.join(cards) or '<div class="empty">Nenhuma notícia coletada ainda. Aguarde a primeira atualização automática.</div>'}</div><div class="pagination"><span id="counter"></span><div><button id="prev" type="button">← Anterior</button><button id="next" type="button">Próxima →</button></div></div></div><aside class="market-panel" aria-label="Painel de mercados"><div class="market-head"><h2>MERCADOS EM FOCO</h2><span class="market-live">PAINEL EXECUTIVO</span></div><div class="market-grid">{market_rows}</div><p class="market-disclaimer" id="market-status">Carregando cotações disponíveis…</p><p class="market-disclaimer">Dados indicativos, sujeitos a atraso. Índices sem fonte validada ficam indisponíveis; nenhuma cotação é simulada.</p></aside></div><footer class="technical-footer"><div class="footer-inner"><div class="footer-brand"><span>JORNAL DO FABRICIO</span><small>EDIÇÃO EXCLUSIVA · {dt.date.fromisoformat(today):%d/%m/%Y}</small></div><div class="footer-links"><details><summary>Exportação e impressão</summary><p><a class="footer-tool" href="noticias.csv">Exportar CSV ↗</a> &nbsp; <button class="footer-print" onclick="window.print()">Imprimir / Salvar PDF</button></p></details><details><summary>Estado da atualização e avisos técnicos</summary><p>{e(status)} · Rascunho automatizado não certificado</p><p>Última geração: {e(dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes'))} UTC</p></details><details><summary>Critérios e limitações</summary><p>Atualização conforme a agenda configurada no GitHub Actions; o navegador consulta novas versões a cada minuto. Feeds RSS e agregadores; títulos e datas dependem das fontes. Seleção exploratória, sem certificação editorial. Fotografias apenas quando fornecidas ou acessíveis legitimamente nas fontes; nenhuma imagem é inventada. A execução agendada pode atrasar ou falhar. Links levam à publicação original.</p></details></div><div class="footer-bottom">© Jornal do Fabricio · Publicação pública · Informações sujeitas à verificação nas fontes originais.</div></div></footer></main><script>
const strip=document.querySelector('#world-strip');if(strip){{const jump=()=>Math.max(210,(strip.querySelector('.world-item')?.getBoundingClientRect().width||210)+10);document.querySelector('#world-prev').onclick=()=>strip.scrollBy({{left:-jump(),behavior:'smooth'}});document.querySelector('#world-next').onclick=()=>strip.scrollBy({{left:jump(),behavior:'smooth'}});let sx=0,sl=0;strip.addEventListener('pointerdown',ev=>{{if(ev.pointerType==='mouse'){{sx=ev.clientX;sl=strip.scrollLeft;}}}});strip.addEventListener('pointerup',ev=>{{if(ev.pointerType==='mouse'&&Math.abs(ev.clientX-sx)>35){{strip.scrollLeft=sl+sx-ev.clientX;}}}});}}
const cards=[...document.querySelectorAll('.story')],search=document.querySelector('#search'),sector=document.querySelector('#sector'),day=document.querySelector('#day');let page=0,matching=[];
function render(reset=true){{if(reset)page=0;let term=search.value.trim().toLocaleLowerCase('pt-BR');matching=cards.filter(x=>(!term||x.dataset.text.includes(term))&&(!sector.value||x.dataset.sector.split('|').includes(sector.value))&&(!day.value||x.dataset.day===day.value));let total=Math.max(1,Math.ceil(matching.length/30));page=Math.max(0,Math.min(page,total-1));cards.forEach(x=>x.hidden=true);matching.slice(page*30,(page+1)*30).forEach(x=>x.hidden=false);document.querySelector('#counter').textContent=`Página ${{page+1}} de ${{total}} · ${{matching.length}} notícias`;document.querySelector('#prev').disabled=page===0;document.querySelector('#next').disabled=page>=total-1;}}
[search,sector,day].forEach(x=>x.addEventListener(x===search?'input':'change',()=>render()));document.querySelector('#prev').onclick=()=>{{page--;render(false);window.scrollTo(0,180)}};document.querySelector('#next').onclick=()=>{{page++;render(false);window.scrollTo(0,180)}};render();
async function refreshMarkets(){{try{{const r=await fetch('mercados.json?t='+Date.now(),{{cache:'no-store'}});if(!r.ok)throw Error('http');const data=await r.json();for(const item of data.items||[]){{const row=[...document.querySelectorAll('.market-row')].find(x=>x.dataset.symbol===item.symbol);if(!row)continue;row.querySelector('.market-value').textContent=item.value||'—';const ch=row.querySelector('.market-change');ch.textContent=item.value?((Number.isFinite(item.change)?(item.change>0?'+':'')+item.change.toFixed(2)+'% · ':'')+(item.status==='último fechamento'?'Fechamento':'Última cotação')+(item.asof?' · '+item.asof:'')):'Indisponível';ch.className='market-change '+(item.change>0?'up':item.change<0?'down':'');}}const time=new Date(data.checked_at);document.querySelector('#market-status').textContent='Consulta: '+(isNaN(time)?'indisponível':time.toLocaleString('pt-BR',{{timeZone:'America/Sao_Paulo'}}))+' (Brasília). Atualização da tela: 30 segundos.';}}catch(err){{document.querySelector('#market-status').textContent='Painel temporariamente indisponível.';}}}}refreshMarkets();setInterval(refreshMarkets,30000);
let version='';async function check(){{try{{let r=await fetch('version.json?ts='+Date.now(),{{cache:'no-store'}});if(!r.ok)return;let v=(await r.json()).version;if(version&&v!==version)location.reload();version=v;}}catch(e){{}}}}check();setInterval(check,60000);
</script></body></html>'''
    (BASE/'index.html').write_text(page,encoding='utf-8')
    (BASE/'version.json').write_text(json.dumps({'version':dt.datetime.now(dt.timezone.utc).isoformat()}))
    with (BASE/'noticias.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['Título','Fonte','Data UTC','Editorias','Link']);w.writerows([a['title'],a['source'],a['published'],', '.join(a['sectors']),a['url']] for a in arts)
    print('Site gerado:',len(arts),'notícias,',count,'imagens locais,',len(page),'caracteres')
if __name__=='__main__':main()
