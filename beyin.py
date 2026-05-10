from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
from openai import OpenAI
import requests

app = FastAPI()

# 🚨 GÜVENLİK DUVARI ŞİFRESİ
SISTEM_GUVENLIK_SIFRESI = "PROHUMMER_2026_SECRET_KEY"
META_VERIFY_TOKEN = "PROHUMMER_META_ONAY_KODU" # Meta'da Webhook kurarken bunu gireceksin

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
    data = load_data()
    if "sohbetler" not in data: # Yeni Sohbet Modülü
        data["sohbetler"] = {}
    return data

@app.post("/api/db")
def update_db(data: dict, x_token: str = Header(None)):
    guvenlik_kontrolu(x_token)
    save_data(data)
    return {"status": "success"}

# --- Orijinal Bot Simülatörü Endpoints (BOZULMADI) ---
@app.post("/api/bot/mesaj")
def bot_mesaji(req: BotRequest, x_token: str = Header(None)):
    guvenlik_kontrolu(x_token)
    try:
        client = OpenAI(api_key=req.api_key)
        messages = [{"role": "system", "content": req.prompt}] + req.mesaj_gecmisi
        response = client.chat.completions.create(model=req.model, messages=messages)
        bot_cevabi = response.choices[0].message.content
        yeni_siparis = None
        asil_mesaj = bot_cevabi

        if "[SIPARIS:" in bot_cevabi:
            asil_mesaj = bot_cevabi.split("[SIPARIS:")[0].strip()
            siparis_detayi = bot_cevabi.split("[SIPARIS:")[1].replace("]", "").strip()
            parcalar = [p.strip() for p in siparis_detayi.split("|")]
            data = load_data()
            if "siparisler" not in data: data["siparisler"] = []
            sip_id = max([s.get("id", 0) for s in data.get("siparisler", [])] + [0]) + 1
            yeni_siparis = {
                "id": sip_id, "isim": parcalar[0] if len(parcalar) > 0 else "Bilinmiyor",
                "tel": parcalar[1] if len(parcalar) > 1 else "—", "adres": parcalar[2] if len(parcalar) > 2 else "—",
                "urun": parcalar[3] if len(parcalar) > 3 else "—", "urunId": "", "adet": 1, 
                "not": "Bot üzerinden alındı", "durum": "Yeni Bekliyor", "tarih": "Bugün", "kaynak": "WhatsApp Bot"
            }
            data["siparisler"].append(yeni_siparis)
            save_data(data)
        return {"cevap": asil_mesaj, "yeni_siparis": yeni_siparis, "ham_cevap": bot_cevabi}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================================================
# YENİ EKLENEN: META (WHATSAPP) GERÇEK CANLI DESTEK KÖPRÜSÜ
# ========================================================

# 1. Meta'nın Webhook Onaylaması İçin (GET)
@app.get("/api/webhook")
def meta_webhook_verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode and token:
        if mode == "subscribe" and token == META_VERIFY_TOKEN:
            return int(challenge)
    raise HTTPException(status_code=403, detail="Onay Basarisiz")

# 2. Meta'dan Gelen Müşteri Mesajlarını Alıp Panele Kaydetme (POST)
@app.post("/api/webhook")
async def meta_webhook_receive(request: Request):
    body = await request.json()
    data = load_data()
    if "sohbetler" not in data:
        data["sohbetler"] = {}

    try:
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if messages:
            msg = messages[0]
            telefon = msg.get("from")
            mesaj_metni = msg.get("text", {}).get("body", "")
            
            # Müşteri veritabanında yoksa oluştur
            if telefon not in data["sohbetler"]:
                data["sohbetler"][telefon] = {
                    "musteri_isim": telefon,
                    "bot_aktif": True, # Başlangıçta bot konuşur
                    "mesajlar": []
                }
            
            # Müşterinin mesajını kaydet
            data["sohbetler"][telefon]["mesajlar"].append({"gonderen": "musteri", "metin": mesaj_metni})
            save_data(data)

            # EĞER BOT AKTİFSE OTOMATİK CEVAP VER:
            if data["sohbetler"][telefon]["bot_aktif"]:
                ayarlar = data.get("ayarlar", {})
                api_key = ayarlar.get("apiKey", "")
                wp_token = ayarlar.get("wpToken", "")
                phone_id = ayarlar.get("wpPhoneId", "")
                prompt = ayarlar.get("prompt", "")

                if api_key and wp_token and phone_id:
                    # OpenAI'ye sor
                    client = OpenAI(api_key=api_key)
                    gecmis = [{"role": "user" if m["gonderen"]=="musteri" else "assistant", "content": m["metin"]} for m in data["sohbetler"][telefon]["mesajlar"][-5:]]
                    ai_mesajlar = [{"role": "system", "content": prompt}] + gecmis
                    res = client.chat.completions.create(model=ayarlar.get("model", "gpt-4o-mini"), messages=ai_mesajlar)
                    bot_cevabi = res.choices[0].message.content

                    # WhatsApp'tan gönder (Meta API)
                    headers = {"Authorization": f"Bearer {wp_token}", "Content-Type": "application/json"}
                    payload = {"messaging_product": "whatsapp", "to": telefon, "type": "text", "text": {"body": bot_cevabi}}
                    requests.post(f"https://graph.facebook.com/v17.0/{phone_id}/messages", headers=headers, json=payload)

                    # Bot cevabını panele kaydet
                    data["sohbetler"][telefon]["mesajlar"].append({"gonderen": "bot", "metin": bot_cevabi})
                    save_data(data)
                    
        return {"status": "ok"}
    except Exception as e:
        print("Webhook Error:", e)
        return {"status": "error"}

# 3. Panelden Personelin Yazdığı Mesajı WhatsApp'a Fırlatma
class PanelMesaj(BaseModel):
    telefon: str
    metin: str

@app.post("/api/chat/gonder")
def panelden_mesaj_gonder(req: PanelMesaj, x_token: str = Header(None)):
    guvenlik_kontrolu(x_token)
    data = load_data()
    ayarlar = data.get("ayarlar", {})
    wp_token = ayarlar.get("wpToken", "")
    phone_id = ayarlar.get("wpPhoneId", "")

    if not wp_token or not phone_id:
        raise HTTPException(status_code=400, detail="Meta API Ayarları Eksik!")

    # Meta API'ye gönder
    headers = {"Authorization": f"Bearer {wp_token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": req.telefon, "type": "text", "text": {"body": req.metin}}
    response = requests.post(f"https://graph.facebook.com/v17.0/{phone_id}/messages", headers=headers, json=payload)
    
    if response.status_code == 200:
        # Başarılıysa panele kaydet
        if req.telefon in data["sohbetler"]:
            data["sohbetler"][req.telefon]["mesajlar"].append({"gonderen": "personel", "metin": req.metin})
            save_data(data)
        return {"status": "success"}
    else:
        raise HTTPException(status_code=500, detail="WhatsApp'a gönderilemedi!")