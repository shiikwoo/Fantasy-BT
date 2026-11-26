import os
import re
import json
import math
import random
import datetime
import urllib.request

# ========================================================
# CONFIGURACAO DA LIGA BRASIL TEAM (SEM ANO FIXO NO CODIGO)
# Pode ser sobrescrito via variavel de ambiente SLEEPER_LEAGUE_ID
# ========================================================
DEFAULT_LEAGUE_ID = "1398124193773527040"
LEAGUE_ID = os.environ.get("SLEEPER_LEAGUE_ID", DEFAULT_LEAGUE_ID).strip() or DEFAULT_LEAGUE_ID
HTML_FILE = "index.html"

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
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def compute_playoff_odds_from_games(season_games, divisions_dict, upcoming_games, seed=2026, n_sims=3000):
    player_to_div = {}
    for div_name, members in divisions_dict.items():
        for p in members:
            player_to_div[p] = div_name

    base = {}
    for p, div_name in player_to_div.items():
        base[p] = {
            "name": p,
            "division": div_name,
            "wins": 0,
            "div_wins": 0,
            "pf": 0.0,
            "pa": 0.0,
            "scores": [],
            "h2h_wins": {},
        }

    for row in season_games:
        _, _, p1, _, pts1, p2, _, pts2, _ = row
        pts1 = float(pts1 or 0.0)
        pts2 = float(pts2 or 0.0)
        if p1 in base and p2 in base:
            base[p1]["pf"] += pts1
            base[p1]["pa"] += pts2
            base[p1]["scores"].append(pts1)
            base[p2]["pf"] += pts2
            base[p2]["pa"] += pts1
            base[p2]["scores"].append(pts2)

            same_div = base[p1]["division"] == base[p2]["division"]
            if pts1 > pts2:
                base[p1]["wins"] += 1
                base[p1]["h2h_wins"][p2] = base[p1]["h2h_wins"].get(p2, 0) + 1
                if same_div:
                    base[p1]["div_wins"] += 1
            elif pts2 > pts1:
                base[p2]["wins"] += 1
                base[p2]["h2h_wins"][p1] = base[p2]["h2h_wins"].get(p1, 0) + 1
                if same_div:
                    base[p2]["div_wins"] += 1

    all_avg = [
        (sum(d["scores"]) / len(d["scores"])) if d["scores"] else 100.0
        for d in base.values()
    ]
    league_avg = sum(all_avg) / len(all_avg) if all_avg else 100.0

    model = {}
    for p, d in base.items():
        n_g = len(d["scores"])
        avg_p = (sum(d["scores"]) / n_g) if n_g > 0 else league_avg
        exp_p = (0.65 * avg_p + 0.35 * league_avg) if n_g > 0 else league_avg
        if n_g > 1:
            var = sum((x - avg_p) ** 2 for x in d["scores"]) / n_g
            sigma = max(16.0, math.sqrt(var))
        else:
            sigma = 22.0
        model[p] = {"exp_pts": exp_p, "sigma": sigma}

    enriched_upcoming = []
    for g in upcoming_games:
        p1, p2, wk = g["p1"], g["p2"], g["week"]
        m1 = model.get(p1, {"exp_pts": league_avg, "sigma": 22.0})
        m2 = model.get(p2, {"exp_pts": league_avg, "sigma": 22.0})
        diff = m1["exp_pts"] - m2["exp_pts"]
        comb_sig = math.sqrt(m1["sigma"] ** 2 + m2["sigma"] ** 2) or 31.0
        raw_prob = 1.0 / (1.0 + math.exp(-1.702 * (diff / comb_sig)))
        wp1 = max(0.05, min(0.95, raw_prob))
        enriched_upcoming.append({
            "week": wk,
            "p1": p1,
            "p2": p2,
            "isDiv": player_to_div.get(p1) == player_to_div.get(p2),
            "proj1": round(m1["exp_pts"], 1),
            "proj2": round(m2["exp_pts"], 1),
            "winProb1": round(wp1, 3),
            "winProb2": round(1.0 - wp1, 3),
        })

    playoff_hits = {p: 0 for p in player_to_div}
    rng = random.Random(seed)

    for _ in range(n_sims):
        sim = {
            p: {
                "name": d["name"],
                "division": d["division"],
                "wins": d["wins"],
                "div_wins": d["div_wins"],
                "pf": d["pf"],
                "pa": d["pa"],
                "h2h": dict(d["h2h_wins"]),
            }
            for p, d in base.items()
        }

        for g in enriched_upcoming:
            a = sim.get(g["p1"])
            b = sim.get(g["p2"])
            if not a or not b:
                continue
            m1 = model.get(g["p1"], {"exp_pts": league_avg, "sigma": 22.0})
            m2 = model.get(g["p2"], {"exp_pts": league_avg, "sigma": 22.0})
            pts_a = max(30.0, rng.gauss(m1["exp_pts"], m1["sigma"]))
            pts_b = max(30.0, rng.gauss(m2["exp_pts"], m2["sigma"]))
            if abs(pts_a - pts_b) < 0.05:
                pts_a += 0.1

            a["pf"] += pts_a
            a["pa"] += pts_b
            b["pf"] += pts_b
            b["pa"] += pts_a

            if pts_a > pts_b:
                a["wins"] += 1
                a["h2h"][g["p2"]] = a["h2h"].get(g["p2"], 0) + 1
                if g["isDiv"]:
                    a["div_wins"] += 1
            else:
                b["wins"] += 1
                b["h2h"][g["p1"]] = b["h2h"].get(g["p1"], 0) + 1
                if g["isDiv"]:
                    b["div_wins"] += 1

        for _, members in divisions_dict.items():
            div_list = [sim[m] for m in members if m in sim]
            div_list.sort(
                key=lambda x: (
                    -x["wins"],
                    -x["div_wins"],
                    -x["pf"],
                    x["pa"],
                )
            )
            if len(div_list) >= 1:
                playoff_hits[div_list[0]["name"]] += 1
            if len(div_list) >= 2:
                playoff_hits[div_list[1]["name"]] += 1

    odds_map = {
        p: round((hits / n_sims) * 100.0, 1)
        for p, hits in playoff_hits.items()
    }
    return odds_map, enriched_upcoming


def main():
    print(f"Conectando a API publica do Sleeper (liga {LEAGUE_ID})...")
    league_data = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}")
    users = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/users")
    rosters = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/rosters")

    season_str = league_data.get("season")
    ano_corrente = int(season_str) if season_str else datetime.date.today().year
    print(f"Temporada detectada automaticamente: {ano_corrente}")

    meta = league_data.get("metadata", {})
    division_names = {
        1: meta.get("division_1", "SMT"),
        2: meta.get("division_2", "NE"),
        3: meta.get("division_3", "MG"),
        4: meta.get("division_4", "SP"),
    }

    user_info = {}
    for u in users:
        uid = u["user_id"]
        uname = u.get("display_name", "")
        tname = u.get("metadata", {}).get("team_name") or f"Team {uname}"
        user_info[uid] = {"username": uname, "team_name": tname}

    roster_map = {}
    divisions_dict = {name: [] for name in division_names.values()}
    rosters_snapshot = []

    for r in rosters:
        rid = r["roster_id"]
        oid = r.get("owner_id")
        div_num = r.get("settings", {}).get("division", 1)
        div_name = division_names.get(div_num, f"Divisao {div_num}")

        info = user_info.get(oid, {"username": f"User_{rid}", "team_name": f"Team {rid}"})
        uname = info["username"]
        player_name = SLEEPER_TO_PLAYER.get(uname, uname)

        roster_map[rid] = {
            "player": player_name,
            "team": info["team_name"],
            "division": div_name,
        }

        if div_name not in divisions_dict:
            divisions_dict[div_name] = []
        divisions_dict[div_name].append(player_name)

        rosters_snapshot.append({
            "rosterId": rid,
            "player": player_name,
            "team": info["team_name"],
            "division": div_name,
            "players": r.get("players") or [],
            "starters": r.get("starters") or [],
            "taxi": r.get("taxi") or [],
            "reserve": r.get("reserve") or [],
        })

    novos_jogos_ano = []
    matchups_closed_by_week = {}
    upcoming_games = []
    max_week_jogada = 0
    playoff_start = int((league_data.get("settings") or {}).get("playoff_week_start") or 15)

    for w in range(1, 18):
        matchups = fetch_json(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/matchups/{w}")
        if not matchups:
            continue

        pontos = [float(m.get("points") or 0.0) for m in matchups]
        duelos = {}
        for m in matchups:
            mid = m.get("matchup_id")
            if mid is not None:
                duelos.setdefault(mid, []).append(m)

        if sum(pontos) > 0:
            max_week_jogada = max(max_week_jogada, w)
            compact_week_entries = []
            for m in matchups:
                rid = m.get("roster_id")
                if rid not in roster_map:
                    continue
                compact_week_entries.append({
                    "roster_id": rid,
                    "player": roster_map[rid]["player"],
                    "matchup_id": m.get("matchup_id"),
                    "points": round(float(m.get("points") or 0.0), 2),
                    "starters": m.get("starters") or [],
                    "starters_points": m.get("starters_points") or [],
                    "players": m.get("players") or [],
                    "players_points": m.get("players_points") or {},
                })
            matchups_closed_by_week[str(w)] = compact_week_entries

            for _, pair in duelos.items():
                if len(pair) == 2:
                    t1, t2 = pair[0], pair[1]
                    p1 = roster_map.get(t1["roster_id"])
                    p2 = roster_map.get(t2["roster_id"])
                    if not p1 or not p2:
                        continue
                    pts1 = round(float(t1.get("points") or 0.0), 2)
                    pts2 = round(float(t2.get("points") or 0.0), 2)
                    fase = "Temporada Regular" if w < playoff_start else "Playoffs"
                    novos_jogos_ano.append([
                        ano_corrente,
                        w,
                        p1["player"],
                        p1["team"],
                        pts1,
                        p2["player"],
                        p2["team"],
                        pts2,
                        fase,
                    ])
        elif w < playoff_start:
            for _, pair in duelos.items():
                if len(pair) == 2:
                    p1 = roster_map.get(pair[0]["roster_id"])
                    p2 = roster_map.get(pair[1]["roster_id"])
                    if p1 and p2:
                        upcoming_games.append({
                            "week": w,
                            "p1": p1["player"],
                            "p2": p2["player"],
                        })

    odds_map, enriched_upcoming = compute_playoff_odds_from_games(
        novos_jogos_ano, divisions_dict, upcoming_games, seed=ano_corrente, n_sims=3000
    )

    snapshot_season = {
        "season": ano_corrente,
        "leagueId": LEAGUE_ID,
        "updatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "maxClosedWeek": max_week_jogada,
        "rosterPositions": league_data.get("roster_positions") or [],
        "scoringSettings": league_data.get("scoring_settings") or {},
        "divisions": divisions_dict,
        "rosters": rosters_snapshot,
        "closedMatchupsByWeek": matchups_closed_by_week,
        "upcomingGames": enriched_upcoming,
        "playoffOddsByPlayer": odds_map,
    }

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    raw_marker = "const RAW_DATA = ["
    schema_marker = ";
// Schema: [0: year"
    idx_raw_start = html.find(raw_marker)
    idx_schema = html.find(schema_marker)
    assert idx_raw_start != -1 and idx_schema != -1, "Marcadores RAW_DATA nao encontrados"

    raw_list = json.loads(html[idx_raw_start + len(raw_marker):idx_schema])
    raw_historico = [r for r in raw_list if r[0] != ano_corrente]
    raw_historico.extend(novos_jogos_ano)
    raw_historico.sort(key=lambda x: (x[0], x[1]))

    div_json = json.dumps(divisions_dict, ensure_ascii=False)
    if "const DIVISIONS_DATA =" in html:
        html = re.sub(r"const DIVISIONS_DATA = \{.*?\};", f"const DIVISIONS_DATA = {div_json};", html, flags=re.DOTALL)
    else:
        html = html.replace(raw_marker, f"const DIVISIONS_DATA = {div_json};
{raw_marker}", 1)

    snap_json = json.dumps(snapshot_season, ensure_ascii=False, separators=(",", ":"))
    if "const SLEEPER_SEASON_SNAPSHOT =" in html:
        html = re.sub(
            r"const SLEEPER_SEASON_SNAPSHOT = .*?;
",
            f"const SLEEPER_SEASON_SNAPSHOT = {snap_json};
",
            html,
            count=1,
            flags=re.DOTALL,
        )
    else:
        html = html.replace(raw_marker, f"const SLEEPER_SEASON_SNAPSHOT = {snap_json};
{raw_marker}", 1)

    hoje = datetime.date.today().strftime("%d/%m/%Y")
    total_jogos = f"{len(raw_historico):,}".replace(",", ".")
    html = re.sub(r"[0-9\.]+ Confrontos", f"{total_jogos} Confrontos", html)
    html = re.sub(r"Atualizado: [0-9/]+ \(Semana \d+\)", f"Atualizado: {hoje} (Semana {max_week_jogada})", html)

    idx_raw_start = html.find(raw_marker)
    idx_schema = html.find(schema_marker)
    novo_raw_json = json.dumps(raw_historico, ensure_ascii=False)
    html = html[:idx_raw_start + len(raw_marker)] + novo_raw_json + html[idx_schema:]

    with open(HTML_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)

    print(f"index.html atualizado com sucesso para a temporada {ano_corrente} (ate Semana {max_week_jogada}).")


if __name__ == "__main__":
    main()
