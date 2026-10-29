#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coleta_amostra.py
Download amostral da telemetria de onibus de Curitiba (espelho C3SL/UFPR).

Fonte: https://dadosabertos.c3sl.ufpr.br/curitibaurbs/
Padrao de arquivo: AAAA_MM_DD_veiculos.json.xz

Exemplos:
  python coleta_amostra.py --dry-run
  python coleta_amostra.py
  python coleta_amostra.py --meses 03 08 09 --anoini 2020 --anofim 2024
  python coleta_amostra.py --aux
"""
import argparse
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    sys.exit("Falta o pacote requests: pip install requests")

BASE_URL = "https://dadosabertos.c3sl.ufpr.br/curitibaurbs/"
RE_ARQUIVO = re.compile(r"(\d{4}_\d{2}_\d{2})_[A-Za-z]+\.json\.xz")
TENTATIVAS = 3
PAUSA_ENTRE = 0.5          # segundos entre arquivos (gentileza com o servidor)
PAUSA_ERRO = 30            # segundos antes de tentar de novo
TIMEOUT_LEITURA = (15, 300)  # (conexao, leitura) em segundos

AUX_POR_MES = ("linhas", "shapeLinha", "tabelaLinha", "pois")


def carregar_indice(sessao):
    r = sessao.get(BASE_URL, timeout=TIMEOUT_LEITURA)
    r.raise_for_status()
    encontrados = {}
    for m in re.findall(r'href="([^"]+\.(?:json\.xz|json\.tar\.gz))"', r.text):
        mm = RE_ARQUIVO.match(m)
        if mm:
            encontrados[m] = mm.group(1)
    return encontrados  # {nome_arquivo: aaaa_mm_dd}


def selecionar(indice, anoini, anofim, meses, incluir_aux):
    alvo = []
    for nome, dia in sorted(indice.items(), key=lambda kv: kv[1]):
        ano, mes, _ = dia.split("_")
        ano = int(ano)
        if not (anoini <= ano <= anofim):
            continue
        if nome.endswith(".json.tar.gz"):
            continue
        tipo = nome.split("_", 3)[-1].replace(".json.xz", "")
        if tipo == "veiculos":
            if mes in meses:
                alvo.append(nome)
        elif incluir_aux and tipo in AUX_POR_MES and mes in meses:
            alvo.append(nome)
    return alvo


def tamanho_remoto(sessao, url):
    try:
        h = sessao.head(url, timeout=(15, 30), allow_redirects=True)
        if h.status_code == 200 and "Content-Length" in h.headers:
            return int(h.headers["Content-Length"])
    except requests.RequestException:
        pass
    return None


def baixar(sessao, nome, pasta, log):
    url = urljoin(BASE_URL, nome)
    ano = nome[:4]
    destino = os.path.join(pasta, ano, nome)
    os.makedirs(os.path.dirname(destino), exist_ok=True)

    tam = tamanho_remoto(sessao, url)
    if os.path.exists(destino):
        local = os.path.getsize(destino)
        if tam is None or local == tam:
            log(f"  [pulado] {nome} (ja existe)")
            return "pulado"
        os.remove(destino)
        log(f"  [rebaixando] {nome} (tamanho divergia)")

    for tentativa in range(1, TENTATIVAS + 1):
        try:
            with sessao.get(url, stream=True, timeout=TIMEOUT_LEITURA) as r:
                if r.status_code == 404:
                    log(f"  [404] {nome} nao existe mais no servidor")
                    return "falhou"
                r.raise_for_status()
                tmp = destino + ".part"
                with open(tmp, "wb") as f:
                    for bloco in r.iter_content(chunk_size=1 << 20):
                        if bloco:
                            f.write(bloco)
                os.replace(tmp, destino)
                if tam is not None and os.path.getsize(destino) != tam:
                    raise IOError("tamanho baixado difere do Content-Length")
                return "baixado"
        except (requests.RequestException, IOError) as e:
            log(f"  [erro {tentativa}/{TENTATIVAS}] {nome}: {e}")
            if os.path.exists(destino + ".part"):
                os.remove(destino + ".part")
            if tentativa < TENTATIVAS:
                time.sleep(PAUSA_ERRO)
    return "falhou"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", default="coleta_curitiba", help="pasta de destino")
    ap.add_argument("--anoini", type=int, default=2017)
    ap.add_argument("--anofim", type=int, default=datetime.now().year)
    ap.add_argument("--meses", nargs="+", default=["03", "08"], help="meses amostrados, ex: 03 08")
    ap.add_argument("--aux", action="store_true", help="baixa tambem linhas/shapeLinha/tabelaLinha dos meses amostrados")
    ap.add_argument("--dry-run", action="store_true", help="so lista; nao baixa nada")
    args = ap.parse_args()

    meses = {f"{int(m):02d}" for m in args.meses}
    sessao = requests.Session()
    sessao.headers.update({"User-Agent": "coleta-telemetria-curitiba (pesquisa academica)"})

    log_path = os.path.join(args.saida, "coleta.log")
    os.makedirs(args.saida, exist_ok=True)

    def log(msg):
        linha = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
        print(linha)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(linha + "\n")

    log(f"Iniciando coleta | meses={sorted(meses)} anos={args.anoini}..{args.anofim} aux={args.aux} dry={args.dry_run}")
    try:
        indice = carregar_indice(sessao)
    except requests.RequestException as e:
        sys.exit(f"Falha ao ler o indice {BASE_URL}: {e}")
    log(f"Indice lido: {len(indice)} arquivos no servidor")

    alvo = selecionar(indice, args.anoini, args.anofim, meses, args.aux)
    log(f"Selecionados: {len(alvo)} arquivos para baixar")

    if args.dry_run:
        por_ano = {}
        for nome in alvo:
            por_ano.setdefault(nome[:4], []).append(nome)
        for ano in sorted(por_ano):
            log(f"  {ano}: {len(por_ano[ano])} arquivos")
        log("Dry-run concluido. Nada foi baixado.")
        return

    contagem = {"baixado": 0, "pulado": 0, "falhou": 0}
    inicio = time.time()
    for i, nome in enumerate(alvo, 1):
        resultado = baixar(sessao, nome, args.saida, log)
        contagem[resultado] += 1
        decorrido = time.time() - inicio
        media = decorrido / i
        restantes = (len(alvo) - i) * media
        log(f"[{i}/{len(alvo)}] {nome} -> {resultado} | ETA ~{restantes/60:.0f} min")
        time.sleep(PAUSA_ENTRE)

    log(f"Concluido: {contagem['baixado']} baixados, {contagem['pulado']} pulados, {contagem['falhou']} falharam")
    if contagem["falhou"]:
        sys.exit(2)


if __name__ == "__main__":
    main()