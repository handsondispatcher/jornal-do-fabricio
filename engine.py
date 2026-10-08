import datetime as dt, email.utils, hashlib, html, json, re, sqlite3, urllib.request, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

BASE=Path(__file__).resolve().parent
TZ=ZoneInfo('America/Sao_Paulo')
SECTORS={'politica':'política congresso governo Brasil','economia':'economia inflação PIB emprego Brasil','financas':'dólar bolsa juros Banco Central Brasil','geopolitica':'Brasil relações internacionais diplomacia','logistica':'logística portos transporte rodovias Brasil','tecnologia':'tecnologia inteligência artificial Brasil','ciencia':'ciência pesquisa descoberta Brasil','empresas':'empresas indústria negócios Brasil','energia':'energia petróleo eletricidade Brasil','agronegocio':'agronegócio safra agricultura Brasil','saude':'saúde medicina vacina Brasil','sociedade':'educação justiça sociedade Brasil','clima':'clima meio ambiente Brasil','esportes':'esportes futebol campeonato brasileiro jogos resultados Brasil','cultura':'cultura cinema música Brasil','internacional':'world breaking news global politics international affairs','americas':'Américas Estados Unidos Canadá México América Latina política economia','europa':'Europa União Europeia Reino Unido França Alemanha política economia','asia':'Ásia China Japão Índia Coreia Taiwan política economia','oriente_medio':'Oriente Médio Israel Palestina Irã Arábia Saudita Emirados Iraque Síria Líbano Iêmen','oceania':'Oceania Austrália Nova Zelândia Pacífico política economia','africa':'África Nigéria África do Sul Quênia Egito União Africana','antartida':'Antártida pesquisa científica clima estações polares','guerra':'guerra conflitos armados ataques cessar-fogo Ucrânia Rússia Gaza Sudão','espaco':'espaço NASA ESA foguetes satélites astronomia exploração espacial'}
DIRECT=[('BBC World','https://feeds.bbci.co.uk/news/world/rss.xml'),('BBC Europe','https://feeds.bbci.co.uk/news/world/europe/rss.xml'),('BBC Asia','https://feeds.bbci.co.uk/news/world/asia/rss.xml'),('BBC US','https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml'),('BBC Africa','https://feeds.bbci.co.uk/news/world/africa/rss.xml'),('BBC Latin America','https://feeds.bbci.co.uk/news/world/latin_america/rss.xml'),('BBC Middle East','https://feeds.bbci.co.uk/news/world/middle_east/rss.xml'),('BBC Science','https://feeds.bbci.co.uk/news/science_and_environment/rss.xml'),('Agência Brasil — Últimas','https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml'),('G1 — Geral','https://g1.globo.com/rss/g1/'),('BBC News Brasil','https://feeds.bbci.co.uk/portuguese/rss.xml')]
# Canais de descoberta, NAO contratos com os veículos nem feeds diretos.
OUTLETS={
'Folha de S.Paulo':'folha.uol.com.br','Estadão':'estadao.com.br','O Globo':'oglobo.globo.com',
'Valor Econômico':'valor.globo.com','Correio Braziliense':'correiobraziliense.com.br',
'Poder360':'poder360.com.br','CNN Brasil':'cnnbrasil.com.br','UOL':'noticias.uol.com.br',
'R7':'noticias.r7.com','SBT News':'sbtnews.sbt.com.br','Band':'band.com.br',
'InfoMoney':'infomoney.com.br','Money Times':'moneytimes.com.br','Brazil Journal':'braziljournal.com',
'InvestNews':'investnews.com.br','Agência Infra':'agenciainfra.com','Portos e Navios':'portosenavios.com.br',
'Transporte Moderno':'transportemoderno.com.br','MundoLogística':'mundologistica.com.br',
'Canaltech':'canaltech.com.br','Tecnoblog':'tecnoblog.net','Olhar Digital':'olhardigital.com.br',
'Agência FAPESP':'agencia.fapesp.br','Jornal da USP':'jornal.usp.br','Fiocruz':'portal.fiocruz.br',
'Globo Rural':'globorural.globo.com','Canal Rural':'canalrural.com.br','Notícias Agrícolas':'noticiasagricolas.com.br',
'DefesaNet':'defesanet.com.br','Poder Aéreo':'aereo.jor.br','Poder Naval':'naval.com.br',
'ge':'ge.globo.com','ESPN Brasil':'espn.com.br','Lance!':'lance.com.br',
'MetSul':'metsul.com','((o))eco':'oeco.org.br','GZH':'gauchazh.clicrbs.com.br',
'O Liberal':'oliberal.com','Diário do Nordeste':'diariodonordeste.verdesmares.com.br',
'Estado de Minas':'em.com.br','A Tarde':'atarde.com.br','Gazeta do Povo':'gazetadopovo.com.br'}

# Cobertura territorial e por especialidade. Cada consulta e um canal de descoberta,
# nao uma redacao independente. A data do feed continua obrigatoria.
REGIONS={
 'Norte':'Acre Amazonas Amapá Pará Rondônia Roraima Tocantins',
 'Nordeste':'Bahia Sergipe Alagoas Pernambuco Paraíba Rio Grande do Norte Ceará Piauí Maranhão',
 'Centro-Oeste':'Distrito Federal Goiás Mato Grosso Mato Grosso do Sul',
 'Sudeste':'São Paulo Rio de Janeiro Minas Gerais Espírito Santo',
 'Sul':'Paraná Santa Catarina Rio Grande do Sul',
}
INTERNATIONAL_QUERIES=[
 'Donald Trump Casa Branca Estados Unidos política externa',
 'China Xi Jinping Taiwan economia comércio',
 'União Europeia Comissão Europeia Parlamento Europeu',
 'guerra Ucrânia Rússia ataques negociações',
 'Israel Gaza Oriente Médio conflito cessar fogo',
 'OTAN NATO segurança internacional',
 'tarifas comerciais Estados Unidos China Europa',
 'eleições governos Europa Reino Unido França Alemanha',
 'geopolítica internacional diplomacia ONU sanções',
 'Ásia Pacífico Coreia Japão China relações internacionais',
]
SPORT_QUERIES=[
 'futebol brasileiro campeonato brasileiro serie A serie B resultados',
 'Corinthians Palmeiras Santos São Paulo futebol',
 'Flamengo Fluminense Vasco Botafogo futebol',
 'Grêmio Internacional Cruzeiro Atlético Mineiro futebol',
 'Bahia Vitória Fortaleza Ceará Sport Náutico Santa Cruz futebol',
 'futebol feminino seleção brasileira futebol',
 'vôlei basquete NBB atletismo tênis automobilismo Brasil',
 'esportes olimpicos paralimpicos Brasil competições',
]
SPECIALIST_OUTLETS={
 'ge.globo.com':'esportes','espn.com.br':'esportes','lance.com.br':'esportes',
 'gazetaesportiva.com':'esportes','olimpiadatododia.com.br':'esportes',
 'terra.com.br/esportes':'esportes','cbf.com.br':'esportes',
 'agencia.fapesp.br':'ciencia','jornal.usp.br':'ciencia',
 'portosenavios.com.br':'logistica','agenciainfra.com':'logistica',
 'canaltech.com.br':'tecnologia','tecnoblog.net':'tecnologia',
 'infomoney.com.br':'financas','moneytimes.com.br':'financas',
 'globorural.globo.com':'agronegocio','canalrural.com.br':'agronegocio',
}
REGIONAL_OUTLETS={
 'AC':['ac24horas.com','agazetadoacre.com'],
 'AL':['gazetaweb.com','tnh1.com.br'],
 'AM':['acritica.com','emtempo.com.br'],
 'AP':['selesnafes.com'],
 'BA':['atarde.com.br','correio24horas.com.br'],
 'CE':['diariodonordeste.verdesmares.com.br','opovo.com.br'],
 'DF':['correiobraziliense.com.br','metropoles.com'],
 'ES':['agazeta.com.br','folhavitoria.com.br'],
 'GO':['opopular.com.br','maisgoias.com.br'],
 'MA':['imirante.com'],
 'MG':['em.com.br','otempo.com.br'],
 'MS':['campograndenews.com.br'],
 'MT':['gazetadigital.com.br','olhardireto.com.br'],
 'PA':['oliberal.com','dol.com.br'],
 'PB':['jornaldaparaiba.com.br','clickpb.com.br'],
 'PE':['jc.uol.com.br','diariodepernambuco.com.br'],
 'PI':['cidadeverde.com','meionews.com'],
 'PR':['gazetadopovo.com.br','bemparana.com.br'],
 'RJ':['odia.ig.com.br','extra.globo.com'],
 'RN':['tribunadonorte.com.br','agorarn.com.br'],
 'RO':['rondoniaovivo.com'],
 'RR':['folhabv.com.br'],
 'RS':['gauchazh.clicrbs.com.br','correiodopovo.com.br'],
 'SC':['nsctotal.com.br','ndmais.com.br'],
 'SE':['infonet.com.br'],
 'SP':['g1.globo.com/sp','diariodesorocaba.com.br'],
 'TO':['gazetadocerrado.com.br'],
}
# Marcadores lexicais conservadores. Classificacao por conteudo prevalece sobre
# o feed generico; uma noticia pode pertencer a mais de uma editoria.
EDITORIAL_PATTERNS={
 'esportes':r'\b(corinthians|palmeiras|flamengo|fluminense|botafogo|vasco|gremio|inter de porto alegre|internacional|santos fc|sao paulo fc|cruzeiro|atletico mineiro|brasileirao|serie [abcd]|campeonato brasileiro|libertadores|sul americana|copa do brasil|futebol|atacante|goleiro|tecnico de futebol|partida|placar|gol|gols|trave|tenis|volei|basquete|nba|nbb|formula 1|grand prix|paralimpic|olimpic|esportiv|atleta|selecao brasileira de futebol)\b',
 'politica':r'\b(congresso|senado|camara dos deputados|presidente da republica|eleicao|eleitoral|governador|prefeito|partido politico|deputado|senador|ministerio|stf|tse)\b',
 'financas':r'\b(ibovespa|dolar|cambio|selic|bolsa de valores|b3|banco central|juros|tesouro direto|acoes|mercado financeiro)\b',
 'economia':r'\b(pib|inflacao|ipca|desemprego|emprego formal|salario minimo|atividade economica)\b',
 'logistica':r'\b(porto|portuario|rodovia|ferrovia|caminhao|frete|logistica|transporte de cargas|aeroporto|hidrovia)\b',
 'tecnologia':r'\b(inteligencia artificial|software|ciberseguranca|tecnologia|semicondutor|startup|aplicativo|data center)\b',
 'ciencia':r'\b(pesquisa cientifica|cientistas|descoberta cientifica|universidade|estudo cientifico|fapesp|laboratorio)\b',
 'saude':r'\b(sus|vacina|hospital|medicamento|doenca|epidemia|saude publica|anvisa)\b',
 'energia':r'\b(petroleo|energia eletrica|energia solar|eolica|hidreletrica|combustivel|aneel)\b',
 'agronegocio':r'\b(safra|agronegocio|agricultura|pecuaria|soja|milho|gado|fertilizante)\b',

 'clima':r'\b(previsao do tempo|chuva|enchente|seca|temperatura|mudanca climatica|meio ambiente|desmatamento)\b',
 'internacional':r'\b(trump|casa branca|washington|estados unidos|xi jinping|pequim|china|taiwan|uniao europeia|parlamento europeu|comissao europeia|ucrania|russia|putin|zelensky|gaza|israel|otan|nato|oriente medio|onu|geopolitic|europa|franca|alemanha|reino unido|iran|teera|coreia do norte)\b',
 'cultura':r'\b(cinema|filme|musica|show|festival cultural|teatro|exposicao|literatura|livro)\b',
}
GEOGRAPHY_PATTERNS={
 'americas':r'\b(trump|washington|estados unidos|eua|canada|mexico|argentina|chile|colombia|venezuela|peru|bolivia|equador|cuba|panama|united states|canadian|latin america)\b',
 'europa':r'\b(europa|europe|uniao europeia|european union|franca|france|alemanha|germany|italia|italy|espanha|spain|reino unido|united kingdom|londres|london|ucrania|ukraine|russia|russia|moscou|moscow|otan|nato|polonia|poland)\b',
 'asia':r'\b(china|chinese|pequim|beijing|japao|japan|india|indian|coreia|korea|taiwan|asia|singapura|singapore)\b',
 'oriente_medio':r'\b(oriente medio|middle east|israel|israeli|gaza|palestina|palestine|iran|iranian|teera|tehran|arabia saudita|saudi|emirados arabes|uae|iraque|iraq|siria|syria|libano|lebanon|iemen|yemen|catar|qatar|jordania|jordan|omã|oman|bahrein|bahrain|kuwait)\b',
 'oceania':r'\b(oceania|australia|australian|nova zelandia|new zealand|fiji|papua nova guine|pacific islands)\b',
 'africa':r'\b(africa|african|sudao|sudan|nigeria|kenya|quenia|egito|egypt|congo|ethiopia|etiopia|africa do sul|south africa|sahel|somalia|libia)\b',
 'antartida':r'\b(antartida|antartica|antarctic|antartico|polo sul|south pole)\b',
}
WAR_PATTERN=r'\b(guerra|warfare|war|conflito armado|armed conflict|bombardeio|bombing|airstrike|ataque aereo|invasao militar|invasion|cessar.fogo|ceasefire|combate|batalha|battle|militares mortos|missil|missile|drone attack|ataque de drones|ofensiva militar)\b'
SPACE_PATTERN=r'\b(nasa|esa|spacex|astronauta|astronaut|foguete|rocket|orbita|orbital|satellite|satelite|telescopio espacial|space telescope|estacao espacial|space station|missao lunar|moon mission|marte|mars rover|exploracao espacial|space exploration)\b'
GLOBAL_QUERIES={
 'internacional':['world breaking news international politics','global diplomacy United Nations latest','international trade sanctions summit'],
 'americas':['United States Trump White House Congress','Canada Mexico Latin America breaking news','South America Argentina Chile Colombia Venezuela news'],
 'europa':['Europe EU European Commission Parliament news','United Kingdom France Germany Italy politics','Eastern Europe Ukraine diplomacy economy'],
 'asia':['China Xi Jinping Taiwan latest','India Japan South Korea news'],
 'oriente_medio':['Middle East Israel Palestine Iran developments','Saudi Arabia UAE Iraq Syria Lebanon Yemen news'],
 'oceania':['Australia New Zealand politics economy','Pacific islands Fiji Papua New Guinea climate'],
 'africa':['Africa African Union latest news','Sudan Congo Nigeria Kenya South Africa news','Sahel Somalia Ethiopia developments'],
 'antartida':['Antarctica research scientific discoveries','Antarctic ice shelf climate research stations'],
 'guerra':['Ukraine Russia war latest ceasefire','Gaza Israel war humanitarian ceasefire','Sudan civil war conflict latest','world armed conflicts fighting peace talks'],
 'espaco':['NASA ESA space exploration discoveries','SpaceX rocket launch space science','astronomy exoplanets space telescopes research'],
}
GLOBAL_DIRECT=[
 ('NASA Breaking News','https://www.nasa.gov/news-release/feed/','espaco'),
 ('ESA News','https://www.esa.int/rssfeed/Our_Activities','espaco'),
]

def editorial_sectors(title, summary='', source='', hinted=None):
    headline=normalized(title)
    matched={sector for sector,pattern in EDITORIAL_PATTERNS.items() if re.search(pattern,headline)}
    if re.search(WAR_PATTERN,headline):matched.add('guerra')
    if re.search(SPACE_PATTERN,headline):matched.add('espaco')
    # A classificação geográfica não é mutuamente exclusiva: conflitos podem atravessar continentes.
    geo={sector for sector,pattern in GEOGRAPHY_PATTERNS.items() if re.search(pattern,headline)}
    matched.update(geo)
    if geo and not (matched-geo):matched.add('internacional')
    if 'guerra' in matched:matched.add('internacional')
    if hinted and hinted!='geral' and (not matched or hinted in GEOGRAPHY_PATTERNS or hinted in ('guerra','espaco','internacional')):
        matched.add(hinted)
    if not matched:
        domain=normalized(source)
        for outlet,sector in SPECIALIST_OUTLETS.items():
            if normalized(outlet) in domain:return {sector}
    return matched or {'geral'}

def diversify(items):
    # Primeiro passe distribui editorias; os demais preservam a ordem editorial.
    # Evita uma pagina inteira de futebol ou politica, sem fabricar noticias.
    buckets={}
    for item in items:
        primary=next((x for x in item['sectors'] if x!='geral'),'geral')
        buckets.setdefault(primary,[]).append(item)
    ordered=[]
    while any(buckets.values()):
        for sector in sorted(buckets,key=lambda k:(k=='geral',-len(buckets[k]),k)):
            if buckets[sector]:ordered.append(buckets[sector].pop(0))
    return ordered

def sources():
    result=[{'name':name,'url':url,'kind':'direto','sector':None} for name,url in DIRECT]
    result.extend({'name':name,'url':url,'kind':'direto','sector':sector} for name,url,sector in GLOBAL_DIRECT)
    for sector,query in SECTORS.items():
        result.append({'name':'Tema: '+sector,'url':'https://news.google.com/rss/search?q='+quote(query+' when:2d')+'&hl=pt-BR&gl=BR&ceid=BR:pt-419','kind':'agregador','sector':sector})
    for name,domain in OUTLETS.items():
        result.append({'name':'Descoberta: '+name,'url':'https://news.google.com/rss/search?q='+quote('site:'+domain+' when:2d')+'&hl=pt-BR&gl=BR&ceid=BR:pt-419','kind':'agregador','sector':None})
    for i,q in enumerate(INTERNATIONAL_QUERIES):
        result.append({'name':f'Mundo / tema {i+1}','url':'https://news.google.com/rss/search?q='+quote(q+' when:2d')+'&hl=pt-BR&gl=BR&ceid=BR:pt-419','kind':'agregador','sector':'internacional'})
    # Cobertura internacional multilíngue; buscas regionais não dependem do filtro brasileiro.
    for sector,queries in GLOBAL_QUERIES.items():
        for i,q in enumerate(queries):
            result.append({'name':f'Global / {sector} / {i+1}', 'url':'https://news.google.com/rss/search?q='+quote(q+' when:2d')+'&hl=en-US&gl=US&ceid=US:en','kind':'agregador','sector':sector})
    for i,q in enumerate(SPORT_QUERIES):
        result.append({'name':f'Esportes especializado {i+1}','url':'https://news.google.com/rss/search?q='+quote(q+' when:2d')+'&hl=pt-BR&gl=BR&ceid=BR:pt-419','kind':'agregador','sector':'esportes'})
    for region,states in REGIONS.items():
        for sector in ('esportes','politica','economia','sociedade'):
            q=f'{sector} {states} noticias when:2d'
            result.append({'name':f'{region} / {sector}','url':'https://news.google.com/rss/search?q='+quote(q)+'&hl=pt-BR&gl=BR&ceid=BR:pt-419','kind':'agregador','sector':sector})
    for uf,domains in REGIONAL_OUTLETS.items():
        for domain in domains:
            q=f'site:{domain} when:2d'
            result.append({'name':f'{uf} / {domain}','url':'https://news.google.com/rss/search?q='+quote(q)+'&hl=pt-BR&gl=BR&ceid=BR:pt-419','kind':'agregador','sector':None})
    for domain,sector in SPECIALIST_OUTLETS.items():
        if domain not in OUTLETS.values():
            q=f'site:{domain} when:2d'
            result.append({'name':f'Especialista / {domain}','url':'https://news.google.com/rss/search?q='+quote(q)+'&hl=pt-BR&gl=BR&ceid=BR:pt-419','kind':'agregador','sector':sector})
    return result

def clean(value):
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',value or ''))).strip()

def date_parse(value):
    try:
        d=email.utils.parsedate_to_datetime(value)
    except (TypeError,ValueError):
        try: d=dt.datetime.fromisoformat((value or '').replace('Z','+00:00'))
        except ValueError: return None
    if not d or not d.tzinfo: return None
    return d.astimezone(dt.timezone.utc)

def fetch(url):
    if urlparse(url).scheme!='https': raise ValueError('Somente HTTPS')
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; JornalBrasilLocal/2.0; RSS reader)','Accept':'application/rss+xml,application/atom+xml,application/xml,text/xml,*/*'})
    with urllib.request.urlopen(req,timeout=12) as r:
        payload=r.read(2_000_001)
    if len(payload)>2_000_000: raise ValueError('Feed excedeu 2 MB')
    return payload

def rss_image(item):
    """Only images explicitly supplied by a feed (no fabricated thumbnails)."""
    candidates=[]
    for tag in ('{http://search.yahoo.com/mrss/}content','{http://search.yahoo.com/mrss/}thumbnail','enclosure','{http://www.itunes.com/dtds/podcast-1.0.dtd}image'):
        for el in item.findall(tag):
            url=el.get('url','') or el.get('href','')
            mime=el.get('type','')
            if tag=='enclosure' and mime and not mime.startswith('image/'):continue
            candidates.append(url)
    description=item.findtext('description') or ''
    candidates.extend(re.findall(r'<img\b[^>]*\bsrc=["\'](https://[^"\']+)',description,re.I))
    for url in candidates:
        url=html.unescape(url).strip()
        parsed=urlparse(url)
        if parsed.scheme=='https' and parsed.hostname and not parsed.username and len(url)<1800:
            return url
    return ''

def parse_feed(raw):
    root=ET.fromstring(raw)
    items=[]
    for item in root.findall('./channel/item'):
        src=item.find('source')
        items.append({'title':clean(item.findtext('title')),'url':(item.findtext('link') or '').strip(),'published':item.findtext('pubDate') or '', 'summary':clean(item.findtext('description') or ''),'publisher':clean(src.text or '') if src is not None else '', 'image_url':rss_image(item)})
    ns={'a':'http://www.w3.org/2005/Atom'}
    for item in root.findall('a:entry',ns):
        link=item.find('a:link',ns)
        items.append({'title':clean(item.findtext('a:title','',ns)),'url':link.get('href','') if link is not None else '', 'published':item.findtext('a:published','',ns) or item.findtext('a:updated','',ns),'summary':clean(item.findtext('a:summary','',ns)),'publisher':'','image_url':''})
    return items

def normalized(text):
    import unicodedata
    text=unicodedata.normalize('NFKD',text.casefold())
    return re.sub('[^a-z0-9 ]',' ',''.join(c for c in text if not unicodedata.combining(c)))

def title_key(title):
    # Identical/near-identical headlines are clustered; different headlines about same event may remain.
    words=[w for w in normalized(title).split() if len(w)>2 and w not in {'para','com','uma','sobre','brasil','apos','entre','dos','das','que','por','seu','sua'}]
    return hashlib.sha256(' '.join(sorted(set(words))).encode()).hexdigest()[:24]

def db_open():
    db=sqlite3.connect(BASE/'news.db',timeout=20)
    db.execute('CREATE TABLE IF NOT EXISTS articles(id TEXT PRIMARY KEY,title TEXT,url TEXT,source TEXT,source_type TEXT,published TEXT,summary TEXT,sector TEXT,event_key TEXT,collected TEXT)')
    if 'image_url' not in [r[1] for r in db.execute('PRAGMA table_info(articles)')]:
        db.execute("ALTER TABLE articles ADD COLUMN image_url TEXT DEFAULT ''")
    db.execute('CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT,started TEXT,finished TEXT,success INTEGER,fail INTEGER,received INTEGER,inserted INTEGER,errors TEXT)')
    db.commit();return db

def enrich_images(db, limit=90):
    """Busca imagens publicas das paginas de origem, sem contornar paywalls.
    Armazena miniaturas localmente para evitar bloqueio de hotlink no navegador.
    """
    from urllib.parse import urljoin
    import ipaddress, socket
    from concurrent.futures import ThreadPoolExecutor, as_completed
    folder=BASE/'thumbnails';folder.mkdir(exist_ok=True)
    candidates=db.execute("SELECT id,url,image_url FROM articles WHERE COALESCE(image_url,'')='' AND url NOT LIKE '%news.google.com/%' ORDER BY published DESC LIMIT ?",(limit,)).fetchall()
    def safe_url(url):
        p=urlparse(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password:return False
        try:
            for info in socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM):
                if not ipaddress.ip_address(info[4][0]).is_global:return False
        except Exception:return False
        return True
    def task(row):
        uid,url,_=row
        try:
            if not safe_url(url):return None
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'})
            with urllib.request.urlopen(req,timeout=4) as r:
                if 'text/html' not in r.headers.get('Content-Type','').lower():return None
                snippet=r.read(150000).decode('utf-8','replace')
                final=r.url
            metas=re.findall(r'<meta\b[^>]*>',snippet,re.I)
            image=None
            for tag in metas:
                if re.search(r'(?:og:image|twitter:image)',tag,re.I):
                    m=re.search(r'\bcontent\s*=\s*["\']([^"\']+)',tag,re.I)
                    if m:image=urljoin(final,html.unescape(m.group(1)));break
            if not image or not safe_url(image):return None
            request=urllib.request.Request(image,headers={'User-Agent':'Mozilla/5.0','Accept':'image/avif,image/webp,image/jpeg,image/png,image/*'})
            with urllib.request.urlopen(request,timeout=5) as r:
                mime=r.headers.get('Content-Type','').split(';')[0].lower()
                if mime not in ('image/jpeg','image/png','image/webp'):return None
                blob=r.read(600001)
            if not 1000<=len(blob)<=600000:return None
            ext={'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp'}[mime]
            filename=uid+ext
            (folder/filename).write_bytes(blob)
            return uid,'/thumb/'+filename
        except Exception:return None
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures=[pool.submit(task,row) for row in candidates]
        for f in as_completed(futures):
            result=f.result()
            if result:db.execute('UPDATE articles SET image_url=? WHERE id=?', (result[1],result[0]))
    db.commit()

def collect():
    now=dt.datetime.now(dt.timezone.utc); today=now.astimezone(TZ).date(); db=db_open()
    successes=[]; failures=[]; received=inserted=0
    configured=sources()
    # Rede em paralelo, gravacao SQLite sequencial para evitar disputa de locks.
    with ThreadPoolExecutor(max_workers=7) as pool:
        pending={pool.submit(lambda x:parse_feed(fetch(x['url'])),src):src for src in configured}
        for future in as_completed(pending):
            source=pending[future]
            try:
                entries=future.result();received+=len(entries);added=0
                for a in entries:
                    date=date_parse(a['published'])
                    if not date or date>now+dt.timedelta(minutes=10):continue
                    if date.astimezone(TZ).date() not in (today,today-dt.timedelta(days=1)):continue
                    if urlparse(a['url']).scheme not in ('https','http'):continue
                    publisher=a['publisher'] or source['name']
                    title=a['title']
                    if source['kind']=='agregador' and a['publisher'] and title.endswith(' - '+a['publisher']):title=title[:-(len(a['publisher'])+3)]
                    if not title:continue
                    key=title_key(title);uid=hashlib.sha256(a['url'].encode()).hexdigest()
                    summary=a['summary'][:700]
                    cur=db.execute('INSERT OR IGNORE INTO articles(id,title,url,source,source_type,published,summary,sector,event_key,collected,image_url) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(uid,title,a['url'],publisher,source['kind'],date.isoformat(),summary,next(iter(sorted(editorial_sectors(title,summary,publisher,source['sector'])))),key,now.isoformat(),a.get('image_url','')))
                    if a.get('image_url'): db.execute("UPDATE articles SET image_url=? WHERE id=? AND (image_url IS NULL OR image_url='')",(a['image_url'],uid))
                    added+=cur.rowcount
                db.commit();inserted+=added
                successes.append({'source':source['name'],'items':len(entries),'new':added})
            except Exception as exc:
                failures.append({'source':source['name'],'error':str(exc)[:180]})
    enrich_images(db, limit=90)
    finished=dt.datetime.now(dt.timezone.utc).isoformat()
    db.execute('INSERT INTO runs(started,finished,success,fail,received,inserted,errors) VALUES(?,?,?,?,?,?,?)',(now.isoformat(),finished,len(successes),len(failures),received,inserted,json.dumps(failures,ensure_ascii=False)))
    db.commit();db.close()
    return {'date':today.isoformat(),'sources_ok':successes,'sources_failed':failures,'received':received,'inserted':inserted,'finished':finished}

def report():
    db=db_open(); today=dt.datetime.now(TZ).date(); cutoff=today-dt.timedelta(days=1)
    rows=db.execute('SELECT title,url,source,source_type,published,summary,sector,event_key,image_url FROM articles ORDER BY published DESC').fetchall()
    groups={}
    for title,url,source,kind,published,summary,sector,key,image_url in rows:
        d=dt.datetime.fromisoformat(published).astimezone(TZ).date()
        if d not in (today,cutoff):continue
        if key not in groups:groups[key]={'title':title,'url':url,'source':source,'kind':kind,'published':published,'summary':summary,'sectors':set(),'sources':set(),'related':[],'image_url':image_url or ''}
        item=groups[key]
        if not item.get('image_url') and image_url:item['image_url']=image_url
        item['sectors'].update(editorial_sectors(title,summary,source,sector));item['sources'].add(source)
        if url!=item['url']:item['related'].append(url)
    articles=[]
    for item in groups.values():
        item['sectors']=sorted(item['sectors']);item['source_count']=len(item.pop('sources'))
        item['related']=item['related'][:5];articles.append(item)
    # Ordenacao exploratoria: mais recente + mencoes de fontes distintas; NAO e ranking editorial certificado.
    articles.sort(key=lambda a:(min(a['source_count'],3),a['published']),reverse=True)
    articles=diversify(articles)
    run=db.execute('SELECT finished,success,fail,received,inserted,errors FROM runs ORDER BY id DESC LIMIT 1').fetchone();db.close()
    last={'finished':run[0],'success':run[1],'fail':run[2],'received':run[3],'inserted':run[4],'errors':json.loads(run[5])} if run else None
    return {'date':today.isoformat(),'status':'RASCUNHO_NAO_CERTIFICADO','articles':articles,'total':len(articles),'sectors_found':sorted({s for a in articles for s in a['sectors']}),'last_run':last,'channels_configured':len(sources())}
