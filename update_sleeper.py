import os
import re
import json
import datetime
import urllib.request

# ========================================================
# CONFIGURAÇÕES DA SUA LIGA
# ========================================================
LEAGUE_ID = "COLOQUE_SEU_LEAGUE_ID_AQUI"
ANO_CORRENTE = 2026
HTML_FILE = "index.html"

# Mapeamento: Username do Sleeper -> Nome Histórico Padrão da Liga
SLEEPER_TO_PLAYER = {
    "sHikwOo": "Francisco",
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

    # 1. Extrair nomes das Divisões definidos no Sleeper
    meta = league_data.get("metadata", {})
    division_names = {
        1: meta.get("division_1", "Divisão 1"),
        2: meta.get("division_2", "Divisão 2"),
        3: meta.get("division_3", "Divisão 3"),
        4: meta.get("division_4", "Divisão 4"),
    }

    # 2. Mapear user_id -> username e team_name
    user_info = {}
    for u in users:
        uid = u["user_id"]
        uname = u.get("display_name", "")
        tname = u.get("metadata", {}).get("team_name") or f"Team {uname}"
        user_info[uid] = {"username": uname, "team_name": tname}

    # 3. Mapear roster_id e agrupar times por Divisão
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

    print("📁 Divisões carregadas do Sleeper:")
    for dname, members in divisions_dict.items():
        print(f"  • {dname}: {', '.join(members)}")

    # 4. Baixar confrontos de todas as semanas
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
                    ANO_CORRENTE,
                    w,
                    p1["player"],
                    p1["team"],
                    pts1,
                    p2["player"],
                    p2["team"],
                    pts2,
                    fase
                ])

    print(f"✅ {len(novos_jogos_ano)} partidas processadas até a Semana {max_week_jogada}.")

    # 5. Atualizar o index.html
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Atualizar RAW_DATA
    idx_raw_start = html.find("const RAW_DATA = [")
    idx_raw_end = html.find(";\n// Schema: [0: year")
    raw_list = json.loads(html[idx_raw_start + len("const RAW_DATA = "):idx_raw_end])

    # Preserva histórico 2016-2025 e injeta o ano atual atualizado
    raw_historico = [r for r in raw_list if r[0] != ANO_CORRENTE]
    raw_historico.extend(novos_jogos_ano)
    raw_historico.sort(key=lambda x: (x[0], x[1]))

    # Atualizar o bloco DIVISIONS_DATA (se já existir no HTML) ou criar
    div_json = json.dumps(divisions_dict, ensure_ascii=False)
    if "const DIVISIONS_DATA =" in html:
        html = re.sub(r"const DIVISIONS_DATA = \{.*?\};", f"const DIVISIONS_DATA = {div_json};", html, flags=re.DOTALL)
    else:
        # Injeta logo antes de RAW_DATA
        html = html.replace("const RAW_DATA = [", f"const DIVISIONS_DATA = {div_json};\nconst RAW_DATA = [")

    # Atualizar total de confrontos e data no cabeçalho
    hoje = datetime.date.today().strftime("%d/%m/%Y")
    total_jogos = f"{len(raw_historico):,}".replace(",", ".")
    html = re.sub(r"[0-9\.]+ Confrontos", f"{total_jogos} Confrontos", html)
    html = re.sub(r"🕒 Atualizado: [0-9/]+ \(Semana \d+\)", f"🕒 Atualizado: {hoje} (Semana {max_week_jogada})", html)

    # Gravar o RAW_DATA atualizado
    idx_raw_start = html.find("const RAW_DATA = [")
    novo_raw_json = json.dumps(raw_historico, ensure_ascii=False)
    html = html[:idx_raw_start + len("const RAW_DATA = ")] + novo_raw_json + html[html.find(";\n// Schema: [0: year"):]

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print("🚀 index.html atualizado com sucesso!")

if __name__ == "__main__":
    main()
