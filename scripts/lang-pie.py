import os, math, io, sys, json
from collections import defaultdict
from github import Github
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

GH_TOKEN = os.getenv("GH_TOKEN")
GH_ACTOR = os.getenv("GH_ACTOR")
STRICT = os.getenv("STRICT", "false").lower() == "true"
EXCLUDE_REPOS = [r.strip() for r in os.getenv("EXCLUDE_REPOS","").split(",") if r.strip()]
MIN_SLICE = float(os.getenv("MIN_SLICE", "0.02"))
OUT_PATH = os.getenv("OUT_PATH", "assets/lang-pie.png")
THEME = os.getenv("THEME","light").lower()
MAX_COMMITS_PER_REPO = int(os.getenv("MAX_COMMITS_PER_REPO","200"))

if not GH_TOKEN or not GH_ACTOR:
    print("GH_TOKEN or GH_ACTOR missing", file=sys.stderr)
    sys.exit(1)

g = Github(GH_TOKEN)
user = g.get_user(GH_ACTOR)

# ---------- helpers ----------
def apply_theme():
    if THEME == "dark":
        plt.rcParams.update({
            "axes.facecolor":"#0d1117",
            "figure.facecolor":"#0d1117",
            "text.color":"#e6edf3",
        })
    elif THEME == "transparent":
        plt.rcParams.update({
            "figure.facecolor": (0,0,0,0),
            "axes.facecolor": (0,0,0,0),
            "text.color":"#222222",
        })
    else:
        plt.rcParams.update({
            "axes.facecolor":"white",
            "figure.facecolor":"white",
            "text.color":"#222222",
        })

# 拡張子→ざっくり言語マップ（必要に応じて追加）
EXT_MAP = {
    ".c":"C", ".h":"C", ".hpp":"C++", ".hh":"C++", ".hxx":"C++", ".cpp":"C++", ".cc":"C++", ".cxx":"C++",
    ".rs":"Rust", ".go":"Go", ".py":"Python", ".rb":"Ruby", ".java":"Java", ".kt":"Kotlin", ".swift":"Swift",
    ".cs":"C#", ".m":"Objective-C", ".mm":"Objective-C++",
    ".ts":"TypeScript", ".tsx":"TypeScript", ".js":"JavaScript", ".jsx":"JavaScript",
    ".sh":"Shell", ".bash":"Shell", ".zsh":"Shell",
    ".php":"PHP", ".r":"R", ".jl":"Julia", ".hs":"Haskell", ".scala":"Scala", ".pl":"Perl", ".lua":"Lua",
    ".sql":"SQL", ".yml":"YAML", ".yaml":"YAML", ".toml":"TOML", ".json":"JSON",
    ".html":"HTML", ".css":"CSS", ".scss":"CSS", ".md":"Markdown"
}

def ext_to_lang(path:str):
    path = path.lower()
    for ext, lang in EXT_MAP.items():
      if path.endswith(ext):
          return lang
    return None

# ---------- collect ----------
agg = defaultdict(int)

def collect_simple(repo):
    # GitHubの「言語」API: 各言語のバイト数
    langs = repo.get_languages() or {}
    for lang, bytes_ in langs.items():
        agg[lang] += int(bytes_)

def collect_strict(repo):
    # author=自分 のコミットを上から最大N件だけ見て、変更ファイルの拡張子から言語をカウント（加算行数基準）
    commits = repo.get_commits(author=GH_ACTOR)
    count = 0
    session = requests.Session()
    session.headers.update({"Authorization": f"token {GH_TOKEN}",
                            "Accept":"application/vnd.github+json"})
    for commit in commits:
        if count >= MAX_COMMITS_PER_REPO: break
        # /repos/{owner}/{repo}/commits/{sha}
        url = f"https://api.github.com/repos/{repo.full_name}/commits/{commit.sha}"
        r = session.get(url, timeout=30)
        if r.status_code != 200: 
            continue
        files = r.json().get("files", [])
        for f in files:
            filename = f.get("filename","")
            lang = ext_to_lang(filename)
            if not lang:
                continue
            additions = int(f.get("additions",0))
            deletions = int(f.get("deletions",0))
            # 追加+削除で重み付け（ざっくり作業量近似）
            agg[lang] += max(1, additions + deletions)
        count += 1

# 収集対象: 自分所有・非fork・非archived・privateもOK(権限範囲内)
repos = user.get_repos(affiliation="owner", sort="pushed")
for repo in repos:
    if repo.fork or repo.archived or repo.name in EXCLUDE_REPOS:
        continue
    try:
        if STRICT:
            collect_strict(repo)
        else:
            collect_simple(repo)
    except Exception as e:
        # 個別repoの失敗は握りつぶして続行
        print(f"warn: {repo.full_name}: {e}", file=sys.stderr)

# ---------- normalize & merge small slices ----------
total = sum(agg.values())
if total <= 0:
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    # 何もデータが無い場合のプレースホルダー
    plt.figure(figsize=(6,6), dpi=200)
    apply_theme()
    plt.text(0.5,0.5,"No data yet", ha="center", va="center", fontsize=18)
    plt.axis("off")
    plt.savefig(OUT_PATH, bbox_inches="tight", transparent=(THEME=="transparent"))
    sys.exit(0)

items = sorted(agg.items(), key=lambda x: x[1], reverse=True)
others_value = 0
kept = []
for lang, val in items:
    if val/total < MIN_SLICE:
        others_value += val
    else:
        kept.append((lang, val))
if others_value > 0:
    kept.append(("Other", others_value))

labels = [k for k,_ in kept]
sizes  = [v for _,v in kept]

# ---------- plot ----------
apply_theme()
plt.figure(figsize=(6.5,6.5), dpi=220)
# 自動色(テーマに任せる)。%表示を付け、視認性のために1本だけexplode
explode = [0.05] + [0]*(len(sizes)-1) if sizes else None
def autopct(pct):
    return f"{pct:.1f}%"

wedges, texts, autotexts = plt.pie(
    sizes, labels=labels, autopct=autopct, startangle=90, pctdistance=0.75, explode=explode
)
plt.title(f"Languages { '(STRICT)' if STRICT else '' }", pad=16)
plt.axis('equal')

# 凡例(小さめ)
plt.legend(wedges, labels, title="Languages", loc="center left", bbox_to_anchor=(1, 0.5), frameon=False)
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
plt.savefig(OUT_PATH, bbox_inches="tight", transparent=(THEME=="transparent"))
