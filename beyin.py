from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
from openai import OpenAI

app = FastAPI()

# 🚨 GÜVENLİK DUVARI ŞİFRESİ (Sadece panel bu şifreyi bilecek)
SISTEM_GUVENLIK_SIFRESI = "PROHUMMER_2026_SECRET_KEY"

# CORS Ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'veri.json')

def load_data():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# GÜVENLİK KONTROLÜ
def guvenlik_kontrolu(x_token: str):
    if x_token != SISTEM_GUVENLIK_SIFRESI:
        raise HTTPException(status_code=401, detail="GÜVENLİK DUVARI: Erişim Engellendi!")

class BotRequest(BaseModel):
    mesaj_gecmisi: list
    api_key: str
    model: str
    prompt: str

@app.get("/api/db")
def get_db(x_token: str = Header(None)):
    guvenlik_kontrolu(x_token)
    return load_data()

@app.post("/api/db")
def update_db(data: dict, x_token: str = Header(None)):
    guvenlik_kontrolu(x_token)
    save_data(data)
    return {"status": "success"}

@app.post("/api/bot/mesaj")
def bot_mesaji(req: BotRequest, x_token: str = Header(None)):
    guvenlik_kontrolu(x_token)
    try:
        client = OpenAI(api_key=req.api_key)
        messages = [{"role": "system", "content": req.prompt}] + req.mesaj_gecmisi
        
        response = client.chat.completions.create(
            model=req.model,
            messages=messages
        )
        
        bot_cevabi = response.choices[0].message.content
        yeni_siparis = None
        asil_mesaj = bot_cevabi

        if "[SIPARIS:" in bot_cevabi:
            asil_mesaj = bot_cevabi.split("[SIPARIS:")[0].strip()
            siparis_detayi = bot_cevabi.split("[SIPARIS:")[1].replace("]", "").strip()
            parcalar = [p.strip() for p in siparis_detayi.split("|")]
            
            data = load_data()
            if "siparisler" not in data:
                data["siparisler"] = []
                
            sip_id = max([s.get("id", 0) for s in data.get("siparisler", [])] + [0]) + 1
            yeni_siparis = {
                "id": sip_id,
                "isim": parcalar[0] if len(parcalar) > 0 else "Bilinmiyor",
                "tel": parcalar[1] if len(parcalar) > 1 else "—",
                "adres": parcalar[2] if len(parcalar) > 2 else "—",
                "urun": parcalar[3] if len(parcalar) > 3 else "—",
                "urunId": "", "adet": 1, "not": "Bot üzerinden alındı",
                "durum": "Yeni Bekliyor", "tarih": "Bugün", "kaynak": "WhatsApp Bot"
            }
            data["siparisler"].append(yeni_siparis)
            save_data(data)

        return {
            "cevap": asil_mesaj,
            "yeni_siparis": yeni_siparis,
            "ham_cevap": bot_cevabi
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))