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
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    print("🔍 Conectando à API pública do Sleeper...")
    league_data = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}")
    users = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/users")
    rosters = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/rosters")

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
        divisions_dict[div_name].append(player_name)

    # 5. Baixar confrontos de todas as semanas da temporada detectada
    novos_jogos_ano = []
    max_week_jogada = 0

    for w in range(1, 18):
        matchups = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/matchups/{w}")
        if not matchups:
            continue

        pontos = [m.get("points", 0) for m in matchups]
        if sum(pontos) == 0:
            continue  # Semana ainda não disputada

        max_week_jogada = max(max_week_jogada, w)

        duelos = {}
        for m in matchups:
            mid = m.get("matchup_id")
            if mid is not None:
                duelos.setdefault(mid, []).append(m)

        for mid, teams in duelos.items():
            if len(teams) == 2:
                t1, t2 = teams[0], teams[1]
                p1 = roster_map[t1["roster_id"]]
                p2 = roster_map[t2["roster_id"]]
                pts1 = round(float(t1.get("points", 0.0)), 2)
                pts2 = round(float(t2.get("points", 0.0)), 2)
                fase = "Temporada Regular" if w <= 14 else "Playoffs"

                novos_jogos_ano.append([
                    ano_corrente, w, p1["player"], p1["team"], pts1,
                    p2["player"], p2["team"], pts2, fase
                ])

    # 6. Atualizar o arquivo HTML
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

    # Atualizar RAW_DATA
    idx_raw_start = html.find("const RAW_DATA = [")
    raw_list = json.loads(html[idx_raw_start + len("const RAW_DATA = "):html.find(";
// Schema: [0: year")])

    raw_historico = [r for r in raw_list if r[0] != ano_corrente]
    raw_historico.extend(novos_jogos_ano)
    raw_historico.sort(key=lambda x: (x[0], x[1]))

    # Atualizar HISTORICAL_DIVISIONS_MAP
    idx_divs_start = html.find("const HISTORICAL_DIVISIONS_MAP = {")
    if idx_divs_start != -1:
        idx_divs_end = html.find("};

let divStageFilter", idx_divs_start)
        if idx_divs_end == -1: idx_divs_end = html.find("};", idx_divs_start)
        if idx_divs_end != -1:
            divs_str = html[idx_divs_start + len("const HISTORICAL_DIVISIONS_MAP = "):idx_divs_end + 1]
            try:
                fixed_str = re.sub(r'(\d{4}):', r'"":', divs_str)
                hist_divs = json.loads(fixed_str)
                hist_divs[str(ano_corrente)] = divisions_dict
                novo_divs_json = json.dumps(hist_divs, ensure_ascii=False, indent=2)
                novo_divs_json = re.sub(r'"(\d{4})":', r':', novo_divs_json)
                html = html[:idx_divs_start + len("const HISTORICAL_DIVISIONS_MAP = ")] + novo_divs_json + html[idx_divs_end + 1:]
            except Exception as e:
                print(f"⚠️ Erro ao atualizar divisões: {e}")

    # Atualizar total de confrontos e data no cabeçalho
    hoje = datetime.date.today().strftime("%d/%m/%Y")
    total_jogos = f"{len(raw_historico):,}".replace(",", ".")
    html = re.sub(r"[0-9\.]+ Confrontos", f"{total_jogos} Confrontos", html)
    html = re.sub(r"🕒 Atualizado: [0-9/]+ \(Semana \d+\)", f"🕒 Atualizado: {hoje} (Semana {max_week_jogada})", html)

    # Injetar o novo array RAW_DATA no HTML
    idx_raw_start = html.find("const RAW_DATA = [")
    novo_raw_json = json.dumps(raw_historico, ensure_ascii=False)
    html = html[:idx_raw_start + len("const RAW_DATA = ")] + novo_raw_json + html[html.find(";
// Schema: [0: year"):]

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"🚀 HTML atualizado e sincronizado com sucesso para a temporada {ano_corrente}!")

if __name__ == "__main__":
    main()
