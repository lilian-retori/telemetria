"""Dashboard histórico: python dashboard_pro.py. Dependência: pandas.
Lentidão não equivale a atraso contra horário programado.
"""
import argparse
import json
import lzma
import re
import unicodedata
from pathlib import Path
import pandas as pd

def normalizar(v):
    return re.sub(r'[^A-Z0-9]', '', unicodedata.normalize('NFKD', str(v)).encode('ascii','ignore').decode().upper())

def ler_json(p):
    opener = lzma.open if p.suffix == '.xz' else open
    with opener(p,'rt',encoding='utf-8-sig') as f: text=f.read()
    try: obj=json.loads(text); rows=obj if isinstance(obj,list) else [obj]
    except json.JSONDecodeError:
        rows=[]
        for line in text.splitlines():
            if line.strip():
                obj=json.loads(line); rows.extend(obj if isinstance(obj,list) else [obj])
    return pd.DataFrame(rows)

def localizar(comp,name):
    for p in [comp/'auditoria'/name,comp/name]:
        if p.exists(): return p
    return None

def preparar(raiz,data):
    comp=raiz/'outputs'/'comparativo'; ext=raiz/'data'/'external'
    avisos=[]; fontes={}
    def externo(tipo):
        p=ext/f'{data}_{tipo}.json.xz'
        if not p.exists(): p=ext/f'{data}_{tipo}.json'
        if not p.exists(): avisos.append(f'Ausente: {data}_{tipo}'); return pd.DataFrame()
        fontes[tipo]=p.name
        return ler_json(p)
    def csv(name,optional=False):
        p=localizar(comp,name)
        if not p:
            if optional: return pd.DataFrame()
            raise FileNotFoundError(name)
        return pd.read_csv(p,encoding='utf-8-sig')
    g=csv('gargalos_classificados.csv')
    cols=['lat_centro','lon_centro','dias_com_lentidao','observacoes_lentas','veiculos_unicos','distancia_parada_m']
    for c in cols: g[c]=pd.to_numeric(g[c],errors='coerce')
    valid=g[cols].notna().all(axis=1)&g.lat_centro.between(-90,90)&g.lon_centro.between(-180,180)
    avisos.append(f'{int((~valid).sum())} células inválidas excluídas')
    g=g.loc[valid].copy(); g['parada_mais_proxima']=g.parada_mais_proxima.fillna('Sem identificação')
    g['terminal_proximo']=g.parada_mais_proxima.map(lambda n:'TERMINAL' in normalizar(n) or 'ESTACAOTUBO' in normalizar(n))
    h=csv('recorrencia_por_celula.csv')
    for c in ['lat_centro','lon_centro','observacoes_lentas']: h[c]=pd.to_numeric(h[c],errors='coerce')
    h=h.dropna(subset=['lat_centro','lon_centro','observacoes_lentas'])
    h=h.loc[h.lat_centro.between(-90,90)&h.lon_centro.between(-180,180)]
    mx=max(1,h.observacoes_lentas.max())
    heat=[[r.lat_centro,r.lon_centro,r.observacoes_lentas/mx] for r in h.itertuples()]
    aud=csv('auditoria_top20.csv',True); perf=csv('perfis_horarios_top20.csv',True)
    audits=[]
    for r in aud.to_dict('records'):
        r['profiles']=perf.loc[perf.GARGALO==r['GARGALO']].to_dict('records') if not perf.empty else []
        audits.append(r)
    stops=externo('pontosLinha'); cad=externo('linhas'); shape=externo('shapeLinha')
    def coordenadas(df):
        for c in ['LAT','LON']:
            df[c]=pd.to_numeric(df[c].astype(str).str.replace(',','.',regex=False),errors='coerce')
        valid=df.LAT.between(-90,90)&df.LON.between(-180,180)
        if (~valid).any(): avisos.append(f'{int((~valid).sum())} coordenadas inválidas excluídas')
        return df.loc[valid].copy()
    paradas=coordenadas(stops)[['LAT','LON']].drop_duplicates().values.tolist() if not stops.empty else []
    counts={}; display={}
    if not aud.empty:
        for text in aud.linhas_dominantes.fillna(''):
            for item in str(text).split('|'):
                m=re.fullmatch(r'\s*(.*?)\s*\((\d+)\)\s*',item)
                if m:
                    key=normalizar(m[1]); counts[key]=counts.get(key,0)+int(m[2]); display[key]=m[1].strip()
    chosen=sorted(counts,key=counts.get,reverse=True)[:12]
    mapping={}; names={}
    if not cad.empty:
        for r in cad.itertuples():
            cod=str(r.COD).strip(); mapping.setdefault(normalizar(r.NOME),set()).add(cod); names[cod]=r.NOME
    codes=set(); ranking=[]
    for key in chosen:
        matched=mapping.get(key,set())
        if len(matched)==1:
            cod=next(iter(matched)); codes.add(cod); ranking.append({'nome':display[key],'cod':cod,'obs':counts[key]})
        else: avisos.append(f'Nome sem correspondência única: {display[key]}')
    routes=[]
    if not shape.empty and codes:
        shape=coordenadas(shape); shape['COD']=shape.COD.astype(str).str.strip()
        if 'SHP' not in shape: raise ValueError('shapeLinha sem SHP: não é seguro agrupar os percursos')
        # Mantém a ordem de leitura; SHP identifica geometria, não sequência.
        for (cod,shp),df in shape.loc[shape.COD.isin(codes)].groupby(['COD','SHP'],sort=False):
            if len(df)>=2: routes.append({'cod':cod,'shp':str(shp),'nome':names.get(cod,cod),'coords':df[['LAT','LON']].values.tolist()})
    dates=[]
    for p in [raiz/'processamento_log.csv',comp/'processamento_log.csv']:
        if p.exists():
            log=pd.read_csv(p)
            for t in log.get('detalhe',[]): dates.extend(re.findall(r'Data (?:inicial|final) encontrada em DTHR: (\d{4}-\d{2}-\d{2})',str(t)))
            break
    periodo=f'{min(dates)} a {max(dates)}' if dates else 'Período das observações não verificado'
    avisos.append('Metadados de '+data+'; geometria histórica não validada dia a dia.')
    avisos.append('Ordem das geometrias preservada do arquivo; SHP não é sequência nem rótulo de sentido.')
    return dict(points=g.to_dict('records'),heat=heat,stops=paradas,routes=routes,audits=audits,ranking=ranking,warnings=avisos,fontes=fontes,period=periodo,date=data)

def gerar(raiz,data,saida):
    payload=preparar(raiz,data)
    strict=json.loads(pd.Series(payload).to_json(force_ascii=False))
    text=json.dumps(strict,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    saida.parent.mkdir(parents=True,exist_ok=True)
    saida.write_text(HTML.replace('__DATA__',text),encoding='utf-8')
    print(f'Gerado: {saida}')
    print(f"Células: {len(payload['points'])}; paradas por coordenada: {len(payload['stops'])}; linhas: {len(payload['ranking'])}; geometrias: {len(payload['routes'])}")
    for w in payload['warnings']: print('AVISO:',w)
    return payload

HTML=r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Curitiba — lentidão histórica</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<style>body{margin:0;font:14px Arial}#map{position:absolute;inset:0}aside{position:absolute;top:10px;left:10px;z-index:1000;width:290px;background:white;padding:14px;border-radius:8px;max-height:85vh;overflow:auto;box-shadow:0 2px 8px #888}h2{font-size:18px}label{display:block;margin-top:10px}select,input[type=range]{width:100%}small{color:#555}.bars{display:flex;align-items:end;height:85px;gap:2px}.bar{background:#b22222;flex:1}.leaflet-popup-content{min-width:270px}@media(max-width:600px){aside{width:210px;max-height:45vh}}</style></head><body><div id="map"></div><aside><h2>Ônibus de Curitiba</h2><div id="period"></div><p><small>Lentidão histórica, não atraso contra horário programado. Centros agregados de células, não posições atuais dos veículos.</small></p>
<label>Classe<select id="cls"><option value="todas">Todas</option><option value="fora_de_parada" selected>Fora de parada (>100 m)</option><option value="parada">Parada (até 30 m)</option><option value="proximo_de_parada">Próximo (30–100 m)</option></select></label>
<label>Dias mínimos: <span id="daysv"></span><input id="days" type="range" min="1" value="25"></label><label>Observações mínimas: <span id="obsv"></span><input id="obs" type="range" min="0" step="100" value="500"></label><label>Veículos mínimos: <span id="vehv"></span><input id="veh" type="range" min="1" value="50"></label>
<label>Parada mais próxima<select id="terminal"><option value="all">Qualquer</option><option value="yes">Terminal ou tubo</option><option value="no">Outra parada</option></select></label><p id="stats"></p>
<label>Top 20<select id="top"><option value="">Selecione um ponto</option></select></label><label>Perfil horário<select id="tipo"></select></label><small>Tipo de dia altera apenas o perfil do Top 20, não os totais do mapa.</small>
<label>Itinerários<select id="route"><option value="all">Todas as linhas selecionadas</option></select></label><small>Top 12 por soma das contagens reportadas na auditoria — não ranking de toda a rede.</small><details><summary>Avisos e fontes</summary><div id="warnings"></div></details></aside>
<script>const P=__DATA__,el=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const colors={parada:'#1a9850',proximo_de_parada:'#fdae61',fora_de_parada:'#d73027'};
const map=L.map('map',{preferCanvas:true}).setView([-25.46,-49.29],11);const streets=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{attribution:'Tiles © Esri',maxZoom:19}).addTo(map),imagery=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'Imagery © Esri',maxZoom:19}),topo=L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)',maxZoom:17});
const points=L.layerGroup().addTo(map),routes=L.layerGroup().addTo(map),buffers=L.layerGroup(),audit=L.layerGroup(),heat=L.heatLayer(P.heat,{radius:18,blur:15,max:1,minOpacity:.3});let buffersReady=false;map.on('overlayadd',e=>{if(e.layer===buffers&&!buffersReady){P.stops.forEach(p=>L.circle(p,{radius:30,color:'#1a9850',weight:1,fillOpacity:.05}).addTo(buffers));buffersReady=true;}});
const overlays={'Células filtradas':points,'Heatmap total (não filtrado)':heat,'Top 20 auditado':audit};if(P.routes.length)overlays['Itinerários Top 12']=routes;if(P.stops.length)overlays['Buffers 30 m']=buffers;L.control.layers({'Ruas Esri':streets,'Imagem Esri':imagery,'Relevo':topo},overlays).addTo(map);
el('period').textContent=P.period+' | Metadados: '+P.date;el('warnings').innerHTML=P.warnings.map(esc).join('<br>')+'<hr>'+Object.entries(P.fontes).map(([k,v])=>esc(k+': '+v)).join('<br>');
for(const [id,key] of [['days','dias_com_lentidao'],['obs','observacoes_lentas'],['veh','veiculos_unicos']]){const mx=P.points.reduce((m,p)=>Math.max(m,p[key]),1);el(id).max=mx;el(id).value=Math.min(+el(id).value,mx);}
function filtrar(){points.clearLayers();for(const id of ['days','obs','veh'])el(id+'v').textContent=(+el(id).value).toLocaleString('pt-BR');let n=0;for(const p of P.points){if((el('cls').value!=='todas'&&p.classe!==el('cls').value)||p.dias_com_lentidao<+el('days').value||p.observacoes_lentas<+el('obs').value||p.veiculos_unicos<+el('veh').value||(el('terminal').value!=='all'&&p.terminal_proximo!==(el('terminal').value==='yes')))continue;n++;L.circleMarker([p.lat_centro,p.lon_centro],{radius:6,color:colors[p.classe]||'#888',fillOpacity:.8}).bindPopup('<h3>'+esc(p.parada_mais_proxima)+'</h3>Classe: '+esc(p.classe)+'<br>Distância: '+p.distancia_parada_m+' m<br>Dias: '+p.dias_com_lentidao+'<br>Observações lentas: '+p.observacoes_lentas.toLocaleString('pt-BR')+'<br>Veículos únicos: '+p.veiculos_unicos+'<br><small>Proximidade não comprova a causa da lentidão.</small>').addTo(points);}el('stats').textContent=n+' células selecionadas';}
const types=[...new Set(P.audits.flatMap(a=>a.profiles.map(p=>p.TIPO_DIA)))];types.forEach(t=>el('tipo').add(new Option(t,t)));if(types.includes('dia_util'))el('tipo').value='dia_util';
function popup(a){const rows=a.profiles.filter(p=>p.TIPO_DIA===el('tipo').value),by=Object.fromEntries(rows.map(p=>[p.HORA_INT,p.obs_por_dia])),mx=Math.max(1,...rows.map(p=>p.obs_por_dia));const bars=Array.from({length:24},(_,h)=>'<div class="bar" style="background:'+(by[h]===undefined?'#ccc':'#b22222')+';height:'+(by[h]===undefined?2:Math.max(1,100*by[h]/mx))+'%" title="'+h+'h: '+(by[h]===undefined?'registro ausente':by[h].toFixed(2))+'"></div>').join('');return '<h3>'+esc(a.GARGALO)+'</h3><p>'+esc(a.parada_mais_proxima)+'</p>Observações: '+a.obs_lentas_mes.toLocaleString('pt-BR')+'<br>Pico em dia útil: '+a.hora_pico_dia_util+'h<p>'+esc(a.linhas_dominantes)+'</p><p>Observações lentas por dia, por hora — '+esc(el('tipo').value)+'</p><div class="bars">'+bars+'</div><small>0h → 23h; cinza = registro ausente</small>';}
P.audits.forEach((a,i)=>{el('top').add(new Option(a.GARGALO,String(i)));L.circleMarker([a.lat_centro,a.lon_centro],{radius:9,color:'#333',fillColor:'#7b2cbf',fillOpacity:.8}).bindPopup(()=>popup(a)).addTo(audit);});el('top').onchange=()=>{if(el('top').value==='')return;const a=P.audits[+el('top').value];map.setView([a.lat_centro,a.lon_centro],16);L.popup().setLatLng([a.lat_centro,a.lon_centro]).setContent(popup(a)).openOn(map);};el('tipo').onchange=()=>{map.closePopup();if(el('top').value!=='')el('top').onchange();};
P.ranking.forEach(r=>el('route').add(new Option(r.cod+' — '+r.nome,r.cod)));function desenhar(){routes.clearLayers();for(const r of P.routes){if(el('route').value!=='all'&&r.cod!==el('route').value)continue;L.polyline(r.coords,{color:'#08519c',weight:3,opacity:.6}).bindTooltip(esc(r.cod+' — '+r.nome+' | SHP '+r.shp)).addTo(routes);}}el('route').onchange=()=>{desenhar();if(!map.hasLayer(routes))routes.addTo(map);};['cls','days','obs','veh','terminal'].forEach(id=>el(id).addEventListener('input',filtrar));filtrar();desenhar();</script></body></html>'''

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--data-metadados',default='2026_10_07',help='Data YYYY_MM_DD compartilhada pelos três arquivos externos')
    parser.add_argument('--saida',type=Path)
    args=parser.parse_args()
    try: gerar(args.raiz,args.data_metadados,args.saida or args.raiz/'outputs'/'comparativo'/'dashboard_pro.html')
    except Exception as e: raise SystemExit(f'ERRO: {e}')