from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
from openai import OpenAI

app = FastAPI()

# Frontend'in API'ye erişebilmesi için CORS ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Veritabanı yolunu belirle
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

# Gelen istek verileri için model
class BotRequest(BaseModel):
    mesaj_gecmisi: list
    api_key: str
    model: str
    prompt: str

@app.get("/api/db")
def get_db():
    """Tüm veritabanını getirir"""
    return load_data()

@app.post("/api/db")
def update_db(data: dict):
    """Panelden gelen güncellemelerle veritabanını tamamen senkronize eder"""
    save_data(data)
    return {"status": "success"}

@app.post("/api/bot/mesaj")
def bot_mesaji(req: BotRequest):
    """WhatsApp simülatöründen gelen mesajı işler ve OpenAI'a gönderir"""
    try:
        client = OpenAI(api_key=req.api_key)
        
        # Sistem promptunu geçmişin en başına ekliyoruz
        messages = [{"role": "system", "content": req.prompt}] + req.mesaj_gecmisi
        
        response = client.chat.completions.create(
            model=req.model,
            messages=messages
        )
        
        bot_cevabi = response.choices[0].message.content
        yeni_siparis = None
        asil_mesaj = bot_cevabi

        # GİZLİ SİPARİŞ YAKALAYICI
        if "[SIPARIS:" in bot_cevabi:
            asil_mesaj = bot_cevabi.split("[SIPARIS:")[0].strip()
            siparis_detayi = bot_cevabi.split("[SIPARIS:")[1].replace("]", "").strip()
            
            parcalar = [p.strip() for p in siparis_detayi.split("|")]
            
            data = load_data()
            if "siparisler" not in data:
                data["siparisler"] = []
                
            # Yeni siparişe dinamik ID ata
            sip_id = max([s.get("id", 0) for s in data["siparisler"]] + [0]) + 1
            
            yeni_siparis = {
                "id": sip_id,
                "isim": parcalar[0] if len(parcalar) > 0 else "Bilinmiyor",
                "tel": parcalar[1] if len(parcalar) > 1 else "—",
                "adres": parcalar[2] if len(parcalar) > 2 else "—",
                "urun": parcalar[3] if len(parcalar) > 3 else "—",
                "urunId": "", 
                "adet": 1, 
                "not": "Bot üzerinden alındı",
                "durum": "Yeni Bekliyor", 
                "tarih": "Bugün", 
                "kaynak": "WhatsApp Bot"
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