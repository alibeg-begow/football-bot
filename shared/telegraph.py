import os
import requests
import json

TELEGRAPH_API = "https://api.telegra.ph"
TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "telegraph_token.txt")

def get_or_create_token():
    # returns telegraph access_token, creates new account if missing
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            token = f.read().strip()
        if token:
            return token

    try:
        resp = requests.post(f"{TELEGRAPH_API}/createAccount", data={
            "short_name": "MatchBot",
            "author_name": "Match Analysis Bot",
        }, timeout=10)
        data = resp.json()
        if data.get("ok"):
            token = data["result"]["access_token"]
            with open(TOKEN_FILE, "w") as f:
                f.write(token)
            return token
    except Exception:
        pass
        
    return None

def text_to_nodes(text: str) -> list:
    # converts plain text to telegraph node format
    nodes = []
    paragraphs = text.split("\n\n")
    for para in paragraphs:
        lines = [l.strip() for l in para.split("\n") if l.strip()]
        if not lines:
            continue
            
        children = []
        for i, line in enumerate(lines):
            children.append(line)
            if i < len(lines) - 1:
                children.append({"tag": "br"})
        nodes.append({"tag": "p", "children": children})
    return nodes

def create_analysis_page(title: str, content: str) -> str | None:
    # uploads analysis text to telegraph, returns page URL
    token = get_or_create_token()
    if not token:
        return None

    nodes = text_to_nodes(content)
    if not nodes:
        return None

    try:
        resp = requests.post(
            f"{TELEGRAPH_API}/createPage",
            data={
                "access_token": token,
                "title": title[:256],
                "content": json.dumps(nodes, ensure_ascii=False),
                "return_content": "false",
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("ok"):
            return data["result"]["url"]
        else:
            if "TOKEN" in data.get("error", ""):
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                new_token = get_or_create_token()
                if new_token:
                    resp2 = requests.post(
                        f"{TELEGRAPH_API}/createPage",
                        data={
                            "access_token": new_token,
                            "title": title[:256],
                            "content": json.dumps(nodes, ensure_ascii=False),
                            "return_content": "false",
                        },
                        timeout=15,
                    )
                    data2 = resp2.json()
                    if data2.get("ok"):
                        return data2["result"]["url"]
    except Exception:
        pass
        
    return None
