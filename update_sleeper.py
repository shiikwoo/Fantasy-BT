import os
import re
import json
import datetime
import urllib.request

# ========================================================
# CONFIGURAÇÃO DA SUA LIGA BRASIL TEAM
# ========================================================
LEAGUE_ID = "1398124193773527040"
HTML_FILE = "index.html" # IMPORTANTE: Altere aqui para o nome real do seu HTML se necessário no repositório.

# Mapeamento oficial dos 20 técnicos do Sleeper -> Nome Histórico
SLEEPER_TO_PLAYER = {
    "sHiikwOo": "Francisco",
    "JaimeOliveira": "Jaime",
    "Ginmin": "Eduardo",
    "douglasguarda": "Douglas",
    "W4nster": "Wanster",
    "Alceudispor": "Alvin",
    "parah": "Parah",
    "Ricardofmf": "Ricardo",
    "ArionKamitani": "Arion",
    "VitorCorreia": "Vitor",
    "Lubigo7": "Lubigo",
    "Esch85": "Esch",
    "nrjrbr": "Niltomar",
    "poglerr": "Pogliesi",
    "MayeVascaino": "Elivelton",
    "enxurrada": "Arthur",
    "TRCO": "Luprimo",
    "silluis": "Luis Fernando",
    "dsetina": "Daniel",
    "pedrocestaro": "Pedro",
}

def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"⚠️ Erro ao acessar API {url}: {e}")
        return None

def get_safe_points(matchup_dict):
    pts = matchup_dict.get("points")
    return float(pts) if pts is not None else 0.0

def main():
    print("🔍 Conectando à API pública do Sleeper...")
    league_data = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}")
    if not league_data:
        print("❌ Falha crítica: não foi possível carregar os dados da liga. Verifique o LEAGUE_ID.")
        return

    users = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/users") or []
    rosters = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/rosters") or []

    # 1. Puxar o Ano da Temporada diretamente do Sleeper (dinâmico)
    season_str = league_data.get("season")
    ano_corrente = int(season_str) if season_str else datetime.date.today().year
    print(f"📅 Temporada detectada automaticamente no Sleeper: {ano_corrente}")

    # 2. Puxar nomes das Divisões configuradas na liga do Sleeper
    meta = league_data.get("metadata", {})
    division_names = {
        1: meta.get("division_1", "Divisão 1"),
        2: meta.get("division_2", "Divisão 2"),
        3: meta.get("division_3", "Divisão 3"),
        4: meta.get("division_4", "Divisão 4"),
    }

    # 3. Mapear user_id -> username, team_name e AVATARES
    user_info = {}
    avatars_dict = {}
    for u in users:
        uid = u["user_id"]
        uname = u.get("display_name", "")
        tname = u.get("metadata", {}).get("team_name") or f"Team {uname}"
        avatar_hash = u.get("avatar")
        
        user_info[uid] = {"username": uname, "team_name": tname}
        
        player_name = SLEEPER_TO_PLAYER.get(uname, uname)
        if avatar_hash:
            avatars_dict[player_name] = f"https://sleepercdn.com/avatars/thumbs/{avatar_hash}"

    # 4. Mapear roster_id e agrupar participantes por Divisão dinamicamente
    roster_map = {}
    divisions_dict = {name: [] for name in division_names.values()}

    for r in rosters:
        rid = r["roster_id"]
        oid = r.get("owner_id")
        div_num = r.get("settings", {}).get("division", 1)
        div_name = division_names.get(div_num, f"Divisão {div_num}")

        info = user_info.get(oid, {"username": f"User_{rid}", "team_name": f"Team {rid}"})
        uname = info["username"]
        player_name = SLEEPER_TO_PLAYER.get(uname, uname)

        roster_map[rid] = {
            "player": player_name,
            "team": info["team_name"],
            "division": div_name
        }

        if div_name not in divisions_dict:
            divisions_dict[div_name] = []
        if player_name not in divisions_dict[div_name]:
            divisions_dict[div_name].append(player_name)

    # 5. Baixar confrontos de todas as semanas da temporada detectada
    novos_jogos_ano = []
    max_week_jogada = 0

    for w in range(1, 18):
        matchups = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/matchups/{w}")
        if not matchups:
            continue

        # CORREÇÃO CRÍTICA DO ERRO DE NoneType: O Sleeper retorna "points": null para semanas não jogadas.
        pontos = [get_safe_points(m) for m in matchups]
        if sum(pontos) == 0:
            continue  # Semana ainda não disputada ou com zero pontos

        max_week_jogada = max(max_week_jogada, w)

        duelos = {}
        for m in matchups:
            mid = m.get("matchup_id")
            if mid is not None:
                duelos.setdefault(mid, []).append(m)

        for mid, teams in duelos.items():
            if len(teams) == 2:
                t1, t2 = teams[0], teams[1]
                
                rid1 = t1.get("roster_id")
                rid2 = t2.get("roster_id")
                
                if not rid1 or not rid2 or rid1 not in roster_map or rid2 not in roster_map:
                    continue
                    
                p1 = roster_map[rid1]
                p2 = roster_map[rid2]
                
                pts1 = round(get_safe_points(t1), 2)
                pts2 = round(get_safe_points(t2), 2)
                fase = "Temporada Regular" if w <= 14 else "Playoffs"

                novos_jogos_ano.append([
                    ano_corrente, w, p1["player"], p1["team"], pts1,
                    p2["player"], p2["team"], pts2, fase
                ])

    # 6. Atualizar o arquivo HTML
    if not os.path.exists(HTML_FILE):
        print(f"❌ Erro: Arquivo {HTML_FILE} não encontrado no repositório.")
        return

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Injetar os novos Avatares
    idx_avatar_start = html.find("const AVATARES_SLEEPER = {")
    if idx_avatar_start == -1:
        idx_avatar_start = html.find("const AVATARES_SLEEPER = ")
        
    if idx_avatar_start != -1:
        idx_avatar_end = html.find("};", idx_avatar_start)
        if idx_avatar_end != -1:
            novo_avatars_json = json.dumps(avatars_dict, ensure_ascii=False, indent=2)
            html = html[:idx_avatar_start + len("const AVATARES_SLEEPER = ")] + novo_avatars_json + html[idx_avatar_end + 1:]
            print("✅ Dicionário de Avatares (AVATARES_SLEEPER) injetado com sucesso.")

    # Atualizar RAW_DATA (Usando Regex para evitar erro de formatação/quebra de linha)
    match_raw = re.search(r"const RAW_DATA\s*=\s*(\[.*?\]);\s*// Schema:", html, re.DOTALL)
    if match_raw:
        try:
            raw_list = json.loads(match_raw.group(1))
            raw_historico = [r for r in raw_list if r[0] != ano_corrente]
            raw_historico.extend(novos_jogos_ano)
            raw_historico.sort(key=lambda x: (x[0], x[1]))
            
            novo_raw_json = json.dumps(raw_historico, ensure_ascii=False)
            html = html[:match_raw.start(1)] + novo_raw_json + html[match_raw.end(1):]
            print(f"✅ Jogos da temporada {ano_corrente} (até Semana {max_week_jogada}) injetados em RAW_DATA.")
        except json.JSONDecodeError as e:
            print(f"⚠️ Erro ao decodificar RAW_DATA no HTML: {e}")
    else:
        print("⚠️ Erro: Não foi possível localizar const RAW_DATA no HTML.")

    # Atualizar HISTORICAL_DIVISIONS_MAP (Regex)
    match_divs = re.search(r"const HISTORICAL_DIVISIONS_MAP\s*=\s*(\{.*?\});\s*(let divStageFilter|const STANDINGS_DATA|//)", html, re.DOTALL)
    if match_divs:
        divs_str = match_divs.group(1)
        try:
            fixed_str = re.sub(r'(\d{4}):', r'"":', divs_str)
            hist_divs = json.loads(fixed_str)
            hist_divs[str(ano_corrente)] = divisions_dict
            novo_divs_json = json.dumps(hist_divs, ensure_ascii=False, indent=2)
            novo_divs_json = re.sub(r'"(\d{4})":', r':', novo_divs_json)
            
            html = html[:match_divs.start(1)] + novo_divs_json + html[match_divs.end(1):]
            print(f"✅ Divisões da temporada {ano_corrente} injetadas com sucesso.")
        except Exception as e:
            print(f"⚠️ Erro ao atualizar divisões: {e}")
    else:
        print("⚠️ Erro: Não foi possível localizar HISTORICAL_DIVISIONS_MAP no HTML.")

    # Atualizar total de confrontos e data no cabeçalho
    hoje = datetime.date.today().strftime("%d/%m/%Y")
    
    if match_raw:
        try:
            total_jogos = f"{len(raw_historico):,}".replace(",", ".")
            html = re.sub(r"[0-9\.]+ Confrontos", f"{total_jogos} Confrontos", html)
        except NameError:
            pass # Caso raw_historico não tenha sido gerado
    
    html = re.sub(r"🕒 Atualizado: [0-9/]+ \(Semana \d+\)", f"🕒 Atualizado: {hoje} (Semana {max_week_jogada})", html)

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"🚀 Script salvo e atualizado no HTML com sucesso!")

if __name__ == "__main__":
    main()
